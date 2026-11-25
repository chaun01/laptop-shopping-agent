"""Long-term memory: customer preferences persisted in the users table across sessions."""
import json
from typing import Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool

from laptop_agent.db.database import connect, save_preferences


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
    the customer actually stated."""
    user_id = config["configurable"]["user_id"]
    prefs = {"budget_usd": budget_usd, "use_case": use_case, "preferred_brand": preferred_brand,
             "preferred_os": preferred_os, "notes": notes}
    with connect() as conn:
        save_preferences(conn, user_id, prefs)
    return json.dumps({"ok": True, "saved": {k: v for k, v in prefs.items() if v is not None}})
