"""Runtime wrapper used by the CLI, the API and the evals.

`AgentRuntime.chat()` runs one user turn; if the graph pauses for order confirmation it returns
`pending_confirmation`, and `AgentRuntime.resume()` continues it with the customer's yes/no.
"""
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from laptop_agent.agent.graph import build_graph
from laptop_agent.config import get_settings
from laptop_agent.observability import flush, run_config
from laptop_agent.tools.memory import schedule_preference_update


@dataclass
class TurnResult:
    answer: str
    pending_confirmation: dict | None = None
    tool_calls: list[dict] = field(default_factory=list)
    tool_outputs: list[str] = field(default_factory=list)
    guard: dict = field(default_factory=dict)
    latency_s: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0


class AgentRuntime:
    def __init__(self, graph):
        self.graph = graph

    async def chat(self, user_id: str, session_id: str, message: str, tags: list[str] | None = None) -> TurnResult:
        cfg = run_config(user_id, session_id, tags)
        before = await self._n_messages(cfg)
        t0 = time.perf_counter()
        await self.graph.ainvoke({"messages": [HumanMessage(message)]}, cfg)
        result = await self._result(cfg, before, t0)
        self._remember(user_id, message, result.guard)
        return result

    def _remember(self, user_id: str, message: str, guard: dict) -> None:
        if get_settings().prompt_version not in ("v1", "v2") and guard.get("input") == "ok":
            from laptop_agent.guardrails.checks import redact_pii
            schedule_preference_update(user_id, redact_pii(message)[0])   # PII never reaches memory

    async def resume(self, user_id: str, session_id: str, decision: str) -> TurnResult:
        cfg = run_config(user_id, session_id, ["resume"])
        before = await self._n_messages(cfg)
        t0 = time.perf_counter()
        await self.graph.ainvoke(Command(resume=decision), cfg)
        return await self._result(cfg, before, t0)

    async def stream(self, user_id: str, session_id: str, message: str):
        """Yield answer tokens as they are generated (used by the API's SSE endpoint)."""
        cfg = run_config(user_id, session_id, ["stream"])
        async for chunk, meta in self.graph.astream({"messages": [HumanMessage(message)]}, cfg,
                                                    stream_mode="messages"):
            if "agent_answer" in meta.get("tags", []) and chunk.text and not getattr(chunk, "tool_call_chunks", None):
                yield chunk.text
        snap = await self.graph.aget_state(cfg)
        self._remember(user_id, message, snap.values.get("guard", {}))
        flush()

    async def _n_messages(self, cfg) -> int:
        snap = await self.graph.aget_state(cfg)
        return len(snap.values.get("messages", [])) if snap.values else 0

    async def _result(self, cfg, before: int, t0: float) -> TurnResult:
        flush()
        snap = await self.graph.aget_state(cfg)
        msgs = snap.values.get("messages", [])
        new = msgs[before:]
        res = TurnResult(answer="", guard=snap.values.get("guard", {}),
                         latency_s=round(time.perf_counter() - t0, 2))
        for m in new:
            if isinstance(m, ToolMessage):
                res.tool_outputs.append(m.text)
            if isinstance(m, AIMessage):
                res.tool_calls += [{"name": tc["name"], "args": tc["args"]} for tc in m.tool_calls]
                u = m.usage_metadata or {}
                res.input_tokens += u.get("input_tokens", 0)
                res.output_tokens += u.get("output_tokens", 0)
        if snap.interrupts:
            res.pending_confirmation = snap.interrupts[0].value
            res.answer = "Please confirm your order."
        elif msgs and isinstance(msgs[-1], AIMessage):
            res.answer = msgs[-1].text
        return res


@asynccontextmanager
async def open_runtime():
    import asyncio

    from laptop_agent.rag.retriever import warmup
    await asyncio.to_thread(warmup)
    async with AsyncSqliteSaver.from_conn_string(str(get_settings().checkpoint_db)) as saver:
        yield AgentRuntime(build_graph(checkpointer=saver))
