"""Agent-side tools for the cart, backed by the MCP cart server.

The LLM never sees or chooses `user_id`: it is injected from the run config, so a prompt
like "add this to user u002's cart" cannot touch another customer's data.
"""
import json
import os
import sys
from typing import Literal

from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from laptop_agent.config import ROOT

MCP_CART_URL = os.getenv("MCP_CART_URL")   # set in docker-compose; otherwise spawn via stdio


async def call_cart(name: str, args: dict) -> dict:
    async def _call(session: ClientSession) -> dict:
        await session.initialize()
        res = await session.call_tool(name, args)
        if res.isError:
            return {"error": res.content[0].text if res.content else "MCP tool error"}
        if res.structuredContent is not None:
            sc = res.structuredContent
            return sc.get("result", sc) if isinstance(sc, dict) else {"result": sc}
        return json.loads(res.content[0].text)

    if MCP_CART_URL:
        async with streamablehttp_client(MCP_CART_URL) as (r, w, _):
            async with ClientSession(r, w) as s:
                return await _call(s)
    params = StdioServerParameters(command=sys.executable, args=["-m", "laptop_agent.mcp_cart.server"],
                                   env={**os.environ, "PYTHONPATH": str(ROOT / "src")})
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            return await _call(s)


def _user(config: RunnableConfig) -> str:
    uid = (config or {}).get("configurable", {}).get("user_id")
    if not uid:
        raise ValueError("user_id missing from run config")
    return uid


@tool
async def view_cart(config: RunnableConfig) -> str:
    """Show the current user's cart contents and subtotal."""
    return json.dumps(await call_cart("view_cart", {"user_id": _user(config)}))


@tool
async def add_to_cart(product_id: str, config: RunnableConfig, quantity: int = 1) -> str:
    """Add a laptop (by product id, e.g. LP012) to the current user's cart."""
    return json.dumps(await call_cart("add_to_cart", {"user_id": _user(config), "product_id": product_id,
                                                      "quantity": quantity}))


@tool
async def remove_from_cart(product_id: str, config: RunnableConfig) -> str:
    """Remove a laptop from the current user's cart."""
    return json.dumps(await call_cart("remove_from_cart", {"user_id": _user(config), "product_id": product_id}))


@tool
async def place_order(config: RunnableConfig,
                      shipping_option: Literal["standard", "express", "same_day"] = "standard") -> str:
    """Place an order for everything in the cart. Requires explicit customer confirmation (the system
    will pause and ask the customer before this runs)."""
    return json.dumps(await call_cart("place_order", {"user_id": _user(config),
                                                      "shipping_option": shipping_option}))


@tool
async def get_order_status(order_id: str, config: RunnableConfig) -> str:
    """Look up the status of one of the current user's orders (e.g. ORD-1001)."""
    return json.dumps(await call_cart("get_order_status", {"user_id": _user(config), "order_id": order_id}))


CART_TOOLS = [view_cart, add_to_cart, remove_from_cart, place_order, get_order_status]
