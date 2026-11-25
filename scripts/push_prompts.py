"""Publish the versioned system prompts to Langfuse Prompt Management.

Each version gets its own label (v1, v2, ...); the active PROMPT_VERSION also gets `production`.
Usage: python scripts/push_prompts.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from laptop_agent.agent.prompts import PROMPT_NAME, SYSTEM_PROMPTS, to_langfuse_template  # noqa: E402
from laptop_agent.config import get_settings  # noqa: E402
from laptop_agent.observability import _export_env  # noqa: E402

_export_env()
from langfuse import get_client  # noqa: E402

lf, active = get_client(), get_settings().prompt_version
for version in SYSTEM_PROMPTS:
    labels = [version] + (["production"] if version == active else [])
    p = lf.create_prompt(name=PROMPT_NAME, prompt=to_langfuse_template(version), labels=labels, type="text",
                         commit_message=f"system prompt {version}")
    print(f"pushed {PROMPT_NAME} {version} -> Langfuse version {p.version} labels={labels}")
lf.flush()
