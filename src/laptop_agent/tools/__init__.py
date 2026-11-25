from laptop_agent.tools.cart import CART_TOOLS
from laptop_agent.tools.catalog import CATALOG_TOOLS
from laptop_agent.tools.currency import convert_price
from laptop_agent.tools.memory import remember_preference

CORE_TOOLS = CATALOG_TOOLS + CART_TOOLS + [convert_price]
ALL_TOOLS = CORE_TOOLS + [remember_preference]          # every tool the graph can execute


def tools_for(prompt_version: str) -> list:
    """v1/v2 ask the agent to call remember_preference; v3+ handle memory in the background."""
    return ALL_TOOLS if prompt_version in ("v1", "v2") else CORE_TOOLS
