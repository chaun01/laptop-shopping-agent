"""Langfuse tracing. Every graph run becomes one trace with spans for each node, LLM call and
tool call, tagged with user/session, prompt version and model names. No-op when keys are absent."""
import os

from laptop_agent.config import get_settings


def _export_env() -> None:
    s = get_settings()
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", s.langfuse_public_key)
    os.environ.setdefault("LANGFUSE_SECRET_KEY", s.langfuse_secret_key)
    os.environ.setdefault("LANGFUSE_HOST", s.langfuse_host)


def run_config(user_id: str, session_id: str, tags: list[str] | None = None, **metadata) -> dict:
    """Build the LangGraph run config: thread (memory), user (tools), tracing callbacks + metadata."""
    s = get_settings()
    cfg = {
        "configurable": {"thread_id": session_id, "user_id": user_id},
        "recursion_limit": s.recursion_limit,
        "metadata": {
            "langfuse_user_id": user_id,
            "langfuse_session_id": session_id,
            "langfuse_tags": ["laptop-agent", f"prompt:{s.prompt_version}", *(tags or [])],
            "prompt_version": s.prompt_version,
            "llm_model": s.llm_model,
            "llm_fallback_model": s.llm_fallback_model,
            **metadata,
        },
        "callbacks": [],
    }
    if s.tracing_enabled:
        _export_env()
        from langfuse.langchain import CallbackHandler
        cfg["callbacks"].append(CallbackHandler())
    return cfg


def flush() -> None:
    if get_settings().tracing_enabled:
        from langfuse import get_client
        get_client().flush()
