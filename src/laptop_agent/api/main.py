"""HTTP API for the shopping agent.

  GET  /health                 liveness + config summary
  POST /chat                   run one turn -> answer, or pending order confirmation (HITL)
  POST /chat/confirm           resume a paused turn with the customer's yes/no
  POST /chat/stream            Server-Sent Events: answer tokens as they are generated

Run: uvicorn laptop_agent.api.main:app --port 8000
"""
import json
import os
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from laptop_agent.agent.runtime import open_runtime
from laptop_agent.config import get_settings

API_KEY = os.getenv("API_KEY")   # optional shared secret; in production user_id would come from real auth
RATE_LIMIT_PER_MIN = int(os.getenv("RATE_LIMIT_PER_MIN", "20"))
_hits: dict[str, deque] = defaultdict(deque)


def rate_limit(user_id: str) -> None:
    """Sliding-window limit per user (in-process; use Redis when running several API replicas).
    Caps LLM spend per customer and blunts scripted abuse."""
    now, window = time.monotonic(), _hits[user_id]
    while window and now - window[0] > 60:
        window.popleft()
    if len(window) >= RATE_LIMIT_PER_MIN:
        raise HTTPException(429, f"rate limit: max {RATE_LIMIT_PER_MIN} messages per minute")
    window.append(now)


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with open_runtime() as rt:   # warm-up + checkpointer opened once per process
        app.state.rt = rt
        yield


app = FastAPI(title="LaptopHub Shopping Agent", version="1.0", lifespan=lifespan)


def check_key(x_api_key: str | None = Header(default=None)):
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(401, "invalid API key")


class ChatIn(BaseModel):
    user_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    session_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    message: str = Field(min_length=1, max_length=4000)


class ConfirmIn(BaseModel):
    user_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    session_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    decision: str = Field(pattern=r"^(yes|no)$")


@app.get("/health")
async def health():
    s = get_settings()
    return {"status": "ok", "model": s.llm_model, "fallback": s.llm_fallback_model,
            "prompt_version": s.prompt_version, "tracing": s.tracing_enabled,
            "rerank": s.rag_rerank, "parallel_input_guard": s.parallel_input_guard}


@app.post("/chat", dependencies=[Depends(check_key)])
async def chat(body: ChatIn):
    rate_limit(body.user_id)
    try:
        r = await app.state.rt.chat(body.user_id, body.session_id, body.message, tags=["api"])
    except Exception as e:   # never leak stack traces to clients; details are in the trace
        raise HTTPException(503, f"agent unavailable: {type(e).__name__}") from e
    return asdict(r)


@app.post("/chat/confirm", dependencies=[Depends(check_key)])
async def confirm(body: ConfirmIn):
    r = await app.state.rt.resume(body.user_id, body.session_id, body.decision)
    return asdict(r)


@app.post("/chat/stream", dependencies=[Depends(check_key)])
async def chat_stream(body: ChatIn):
    rate_limit(body.user_id)
    rt = app.state.rt

    async def events():
        from laptop_agent.observability import run_config
        cfg = run_config(body.user_id, body.session_id)
        before = await rt._n_messages(cfg)
        t0 = time.perf_counter()
        try:
            async for token in rt.stream(body.user_id, body.session_id, body.message):
                yield f"data: {json.dumps({'token': token})}\n\n"
        except Exception as e:   # LLM outage / quota: end the stream cleanly with a user-safe message
            msg = ("The assistant is temporarily unavailable (model provider error). Please try again in a moment."
                   if "openai" in type(e).__module__ or "APIError" in type(e).__name__
                   else "Something went wrong while answering. Please try again.")
            yield "data: " + json.dumps({"done": True, "error": type(e).__name__, "answer": msg,
                                         "pending_confirmation": None, "tool_calls": [], "guard": {},
                                         "latency_s": round(time.perf_counter() - t0, 2)}) + "\n\n"
            return
        # Final event: the guarded answer (may differ from the streamed draft if the output guard
        # corrected it), whether the graph paused for order confirmation, and turn metadata.
        snap = await rt.graph.aget_state(cfg)
        msgs = snap.values.get("messages", [])
        tools = [{"name": tc["name"]} for m in msgs[before:] for tc in (getattr(m, "tool_calls", None) or [])]
        yield "data: " + json.dumps({
            "done": True, "answer": msgs[-1].text if msgs else "",
            "pending_confirmation": snap.interrupts[0].value if snap.interrupts else None,
            "tool_calls": tools, "guard": snap.values.get("guard", {}),
            "latency_s": round(time.perf_counter() - t0, 2)}) + "\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
