"""Long-term memory: customer preferences persisted in the users table across sessions.

v1/v2 exposed `remember_preference` as an agent tool, which cost an extra LLM round (~5s) on
exactly the turns customers care most about (first recommendation). Prompt v3 moves it off the
critical path: after the answer is returned, a cheap model extracts preferences in the background,
and only when the message looks like it states one (regex pre-filter, so most turns cost nothing).
"""
import asyncio
import json
import re
from typing import Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from pydantic import BaseModel, Field

from laptop_agent.db.database import connect, save_preferences

PREFERENCE_HINT = re.compile(
    r"\$\s?\d|budget|\bmax\b|\bunder\b|student|gaming|programm|editing|travel|business|office|"
    r"mac|windows|\b(dell|hp|lenovo|asus|acer|apple|msi)\b|prefer|only use|i (like|love|hate|need|use)",
    re.IGNORECASE)


class Preferences(BaseModel):
    """Lasting shopping preferences explicitly stated by the customer (leave unknown fields null)."""
    budget_usd: float | None = None
    use_case: str | None = Field(None, description="e.g. programming, gaming, video editing, school")
    preferred_brand: str | None = None
    preferred_os: Literal["Windows 11", "macOS"] | None = None


def looks_like_preference(message: str) -> bool:
    return bool(PREFERENCE_HINT.search(message))


def extract_and_save(user_id: str, message: str) -> dict:
    """Synchronous worker: cheap-model extraction + DB upsert. Returns what was saved."""
    from laptop_agent.llm import get_small_model
    prefs = get_small_model().with_structured_output(Preferences).invoke(
        f"Extract lasting laptop-shopping preferences the customer explicitly states. Message: <<<{message}>>>")
    saved = {k: v for k, v in prefs.model_dump().items() if v not in (None, "")}
    if saved:
        with connect() as conn:
            save_preferences(conn, user_id, saved)
    return saved


_background: set[asyncio.Task] = set()


def schedule_preference_update(user_id: str, message: str) -> None:
    """Fire-and-forget after the answer is sent; failures only lose a memory update, never a reply."""
    if not looks_like_preference(message):
        return

    async def _run():
        try:
            await asyncio.to_thread(extract_and_save, user_id, message)
        except Exception as e:
            print(f"[memory] preference update skipped: {type(e).__name__}")

    task = asyncio.get_running_loop().create_task(_run())
    _background.add(task)                     # keep a reference so the task isn't garbage-collected
    task.add_done_callback(_background.discard)


@tool
def remember_preference(
    config: RunnableConfig,
    budget_usd: float | None = None,
    use_case: str | None = None,
    preferred_brand: str | None = None,
    preferred_os: Literal["Windows 11", "macOS"] | None = None,
    notes: str | None = None,
) -> str:
    """Save a lasting customer preference so future conversations can use it. Only include fields
    the customer actually stated. (Agent tool in prompt v1/v2 only.)"""
    user_id = config["configurable"]["user_id"]
    prefs = {"budget_usd": budget_usd, "use_case": use_case, "preferred_brand": preferred_brand,
             "preferred_os": preferred_os, "notes": notes}
    with connect() as conn:
        save_preferences(conn, user_id, prefs)
    return json.dumps({"ok": True, "saved": {k: v for k, v in prefs.items() if v is not None}})
