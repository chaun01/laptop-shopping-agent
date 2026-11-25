from laptop_agent.tools.cart import CART_TOOLS
from laptop_agent.tools.catalog import CATALOG_TOOLS
from laptop_agent.tools.memory import remember_preference

ALL_TOOLS = CATALOG_TOOLS + CART_TOOLS + [remember_preference]
