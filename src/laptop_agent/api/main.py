"""HTTP API for the shopping agent.

  GET  /health                 liveness + config summary
  POST /chat                   run one turn -> answer, or pending order confirmation (HITL)
  POST /chat/confirm           resume a paused turn with the customer's yes/no
  POST /chat/stream            Server-Sent Events: answer tokens as they are generated

Run: uvicorn laptop_agent.api.main:app --port 8000
"""
import json
import os
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from laptop_agent.agent.runtime import open_runtime
from laptop_agent.config import get_settings

API_KEY = os.getenv("API_KEY")   # optional shared secret; in production user_id would come from real auth


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
    rt = app.state.rt

    async def events():
        async for token in rt.stream(body.user_id, body.session_id, body.message):
            yield f"data: {json.dumps({'token': token})}\n\n"
        # after streaming, tell the client whether the graph paused for order confirmation
        from laptop_agent.observability import run_config
        snap = await rt.graph.aget_state(run_config(body.user_id, body.session_id))
        pending = snap.interrupts[0].value if snap.interrupts else None
        last = snap.values["messages"][-1].text if snap.values.get("messages") else ""
        yield f"data: {json.dumps({'done': True, 'pending_confirmation': pending, 'answer': last})}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")
