"""LLM factory: main model with automatic fallback to a second model.

Run `python -m laptop_agent.llm` for a connectivity smoke test.
"""
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from laptop_agent.config import get_settings


def _chat(model: str) -> ChatOpenAI:
    # gpt-5.x / gpt-6.x only support function tools via the Responses API and
    # reject a custom temperature, so we use the Responses API for every model.
    s = get_settings()
    return ChatOpenAI(model=model, api_key=s.openai_api_key, use_responses_api=True,
                      timeout=s.llm_timeout_s, max_retries=2)


def get_chat_model(tools: list | None = None) -> BaseChatModel:
    """Main model (optionally tool-bound) that falls back to the fallback model on errors."""
    s = get_settings()
    main, backup = _chat(s.llm_model), _chat(s.llm_fallback_model)
    if tools:
        main, backup = main.bind_tools(tools), backup.bind_tools(tools)
    return main.with_fallbacks([backup])


def get_small_model() -> ChatOpenAI:
    """Cheap model for query rewriting, guard classification and LLM-as-judge."""
    return _chat(get_settings().llm_small_model)


def get_embeddings() -> OpenAIEmbeddings:
    s = get_settings()
    return OpenAIEmbeddings(model=s.embedding_model, api_key=s.openai_api_key)


if __name__ == "__main__":
    s = get_settings()
    if not s.openai_api_key:
        raise SystemExit("OPENAI_API_KEY is missing. Copy .env.example to .env and fill it in.")
    reply = get_chat_model().invoke("Reply with exactly: hello from laptop-agent")
    print(f"[{s.llm_model}] {reply.content}")
    print(f"[{s.embedding_model}] dim={len(get_embeddings().embed_query('test'))}")
