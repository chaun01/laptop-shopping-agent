"""MCP server exposing the shopping cart and order system.

Runs as a separate process so the cart/order backend is decoupled from the agent and can be
reused by any MCP client (Claude Desktop, other agents, ...).

  stdio (default, spawned by the agent):  python -m laptop_agent.mcp_cart.server
  HTTP  (docker / shared service):        python -m laptop_agent.mcp_cart.server --http --port 8765
"""
import sys
import uuid
from typing import Literal

from mcp.server.fastmcp import FastMCP

from laptop_agent.db.database import connect, rows

mcp = FastMCP("laptophub-cart", log_level="WARNING")

SHIPPING_COST = {"standard": 15.0, "express": 25.0, "same_day": 40.0}
FREE_STANDARD_SHIPPING_ABOVE = 500.0
MAX_QTY = 5


def _user_exists(conn, user_id: str) -> bool:
    return conn.execute("SELECT 1 FROM users WHERE id = ?", (user_id,)).fetchone() is not None


def _cart(conn, user_id: str) -> dict:
    items = rows(conn.execute(
        """SELECT c.product_id, p.name, c.quantity, p.price_usd, p.stock,
                  c.quantity * p.price_usd AS line_total
           FROM cart_items c JOIN products p ON p.id = c.product_id WHERE c.user_id = ?""", (user_id,)))
    return {"items": items, "subtotal_usd": round(sum(i["line_total"] for i in items), 2)}


@mcp.tool()
def view_cart(user_id: str) -> dict:
    """Show the items in the user's cart with prices and subtotal."""
    with connect() as conn:
        if not _user_exists(conn, user_id):
            return {"error": "unknown user"}
        return _cart(conn, user_id)


@mcp.tool()
def add_to_cart(user_id: str, product_id: str, quantity: int = 1) -> dict:
    """Add a laptop to the cart (quantity 1-5). Fails if the laptop is out of stock."""
    if not 1 <= quantity <= MAX_QTY:
        return {"error": f"quantity must be between 1 and {MAX_QTY}"}
    with connect() as conn:
        if not _user_exists(conn, user_id):
            return {"error": "unknown user"}
        p = conn.execute("SELECT name, stock FROM products WHERE id = ?", (product_id,)).fetchone()
        if p is None:
            return {"error": f"product {product_id} does not exist"}
        cur = conn.execute("SELECT quantity FROM cart_items WHERE user_id = ? AND product_id = ?",
                           (user_id, product_id)).fetchone()
        new_qty = (cur["quantity"] if cur else 0) + quantity
        if p["stock"] < new_qty:
            return {"error": f"only {p['stock']} unit(s) of {p['name']} in stock"}
        if new_qty > MAX_QTY:
            return {"error": f"max {MAX_QTY} units per product"}
        conn.execute("INSERT INTO cart_items VALUES (?,?,?) ON CONFLICT(user_id, product_id) "
                     "DO UPDATE SET quantity = excluded.quantity", (user_id, product_id, new_qty))
        return {"ok": True, "added": p["name"], "cart": _cart(conn, user_id)}


@mcp.tool()
def remove_from_cart(user_id: str, product_id: str) -> dict:
    """Remove a laptop from the cart."""
    with connect() as conn:
        n = conn.execute("DELETE FROM cart_items WHERE user_id = ? AND product_id = ?",
                         (user_id, product_id)).rowcount
        return {"ok": n > 0, "cart": _cart(conn, user_id)}


@mcp.tool()
def place_order(user_id: str, shipping_option: Literal["standard", "express", "same_day"] = "standard") -> dict:
    """Place an order for everything in the cart. Re-checks stock and computes shipping atomically."""
    with connect() as conn:
        cart = _cart(conn, user_id)
        if not cart["items"]:
            return {"error": "cart is empty"}
        for i in cart["items"]:
            if i["stock"] < i["quantity"]:
                return {"error": f"{i['name']} no longer has enough stock ({i['stock']} left)"}
        shipping = 0.0 if shipping_option == "standard" and cart["subtotal_usd"] > FREE_STANDARD_SHIPPING_ABOVE \
            else SHIPPING_COST[shipping_option]
        total = round(cart["subtotal_usd"] + shipping, 2)
        order_id = f"ORD-{uuid.uuid4().hex[:6].upper()}"
        conn.execute("INSERT INTO orders (id, user_id, status, total_usd, shipping_option) VALUES (?,?,?,?,?)",
                     (order_id, user_id, "placed", total, shipping_option))
        for i in cart["items"]:
            conn.execute("INSERT INTO order_items VALUES (?,?,?,?)",
                         (order_id, i["product_id"], i["quantity"], i["price_usd"]))
            conn.execute("UPDATE products SET stock = stock - ? WHERE id = ?", (i["quantity"], i["product_id"]))
        conn.execute("DELETE FROM cart_items WHERE user_id = ?", (user_id,))
        return {"ok": True, "order_id": order_id, "items": cart["items"], "subtotal_usd": cart["subtotal_usd"],
                "shipping_usd": shipping, "total_usd": total, "status": "placed"}


@mcp.tool()
def get_order_status(user_id: str, order_id: str) -> dict:
    """Look up one of the user's orders. Users can only see their own orders."""
    with connect() as conn:
        o = conn.execute("SELECT * FROM orders WHERE id = ? AND user_id = ?", (order_id, user_id)).fetchone()
        if o is None:
            return {"error": "order not found"}
        items = rows(conn.execute("SELECT oi.product_id, p.name, oi.quantity, oi.unit_price_usd FROM order_items oi "
                                  "JOIN products p ON p.id = oi.product_id WHERE order_id = ?", (order_id,)))
        return {**dict(o), "items": items}


if __name__ == "__main__":
    if "--http" in sys.argv:
        port = int(sys.argv[sys.argv.index("--port") + 1]) if "--port" in sys.argv else 8765
        mcp.settings.host, mcp.settings.port = "0.0.0.0", port
        mcp.run(transport="streamable-http")
    else:
        mcp.run()
