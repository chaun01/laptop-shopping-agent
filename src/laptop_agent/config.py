"""Central configuration, loaded from environment / .env (12-factor style)."""
from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / ".env", extra="ignore")

    # LLM
    openai_api_key: str = ""
    llm_model: str = "gpt-6.2-astra"          # main agent model (newest generation)
    llm_fallback_model: str = "gpt-5.4"       # 2nd best in eval; different generation -> survives a model-specific outage
    llm_small_model: str = "gpt-5.4-nano"     # cheap model: query rewrite, guard classifier, judge
    embedding_model: str = "text-embedding-3-small"
    llm_timeout_s: int = 60

    # Storage
    db_path: Path = ROOT / "data" / "shop.db"
    qdrant_path: Path = ROOT / "data" / "qdrant"
    checkpoint_db: Path = ROOT / "data" / "checkpoints.db"
    cache_db: Path = ROOT / "data" / "cache.db"

    # Agent behaviour
    # Performance switches (chosen from eval results, see evals/reports/)
    rag_rerank: bool = False                  # LLM rerank: +1pt P@5 for +2.5s -> off by default
    rag_rewrite: str = "auto"                 # always | auto (skip when the agent already passed filters) | never
    parallel_input_guard: bool = True         # run the LLM input classifier concurrently with the agent

    recursion_limit: int = 12                 # hard cap on graph steps -> no infinite loops
    hitl_order_threshold_usd: float = 0.0     # every order needs human confirmation
    max_input_chars: int = 2000

    # Observability (Langfuse Cloud). Tracing is skipped when keys are empty.
    langfuse_public_key: str = ""
    langfuse_secret_key: str = ""
    langfuse_host: str = "https://cloud.langfuse.com"
    prompt_version: str = "v2"

    @field_validator("openai_api_key", "langfuse_public_key", "langfuse_secret_key", "langfuse_host")
    @classmethod
    def _strip_quotes(cls, v: str) -> str:
        # secrets pasted into CI/env with surrounding quotes are a common, confusing 401 cause
        return v.strip().strip('"').strip("'")

    @property
    def tracing_enabled(self) -> bool:
        return bool(self.langfuse_public_key and self.langfuse_secret_key)


@lru_cache
def get_settings() -> Settings:
    return Settings()
