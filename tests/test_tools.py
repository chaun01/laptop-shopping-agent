import json

import pytest

from laptop_agent.tools.cart import call_cart
from laptop_agent.tools.catalog import check_stock_price, compare_products, get_product_details


def test_product_details_reports_missing_ids():
    out = json.loads(get_product_details.invoke({"product_ids": ["LP001", "LP999"]}))
    assert out["products"][0]["id"] == "LP001" and out["not_found"] == ["LP999"]


def test_compare_requires_2_to_4_ids():
    assert "error" in json.loads(compare_products.invoke({"product_ids": ["LP001"]}))
    out = json.loads(compare_products.invoke({"product_ids": ["LP001", "LP002", "LP003"]}))
    assert set(out["winners"]) == {"cheapest", "lightest", "longest_battery", "most_ram", "best_rated"}


def test_check_stock_unknown_product():
    assert "error" in json.loads(check_stock_price.invoke({"product_id": "XX"}))


@pytest.mark.asyncio
async def test_mcp_cart_flow(temp_db):
    import sqlite3
    con = sqlite3.connect(temp_db)
    in_stock = con.execute("SELECT id, stock FROM products WHERE stock >= 2 LIMIT 1").fetchone()
    oos = con.execute("SELECT id FROM products WHERE stock = 0 LIMIT 1").fetchone()[0]
    con.close()

    assert "error" in await call_cart("add_to_cart", {"user_id": "u002", "product_id": oos, "quantity": 1})
    assert "error" in await call_cart("add_to_cart", {"user_id": "u002", "product_id": in_stock[0], "quantity": 9})
    added = await call_cart("add_to_cart", {"user_id": "u002", "product_id": in_stock[0], "quantity": 1})
    assert added["ok"] and len(added["cart"]["items"]) == 1

    order = await call_cart("place_order", {"user_id": "u002", "shipping_option": "express"})
    assert order["ok"] and order["shipping_usd"] == 25.0
    assert (await call_cart("view_cart", {"user_id": "u002"}))["items"] == []
    # users cannot read other users' orders
    assert "error" in await call_cart("get_order_status", {"user_id": "u002", "order_id": "ORD-1001"})
    con = sqlite3.connect(temp_db)
    assert con.execute("SELECT stock FROM products WHERE id = ?", (in_stock[0],)).fetchone()[0] == in_stock[1] - 1


def test_convert_price_live_and_fallback(monkeypatch):
    import httpx
    from laptop_agent.tools import currency as fx

    class Resp:
        def raise_for_status(self): pass
        def json(self): return {"result": "success", "rates": {"VND": 25000, "EUR": 0.9}, "time_last_update_utc": "t"}

    fx._cache.update(rates=None, fetched_at=0.0)
    monkeypatch.setattr(httpx, "get", lambda *a, **k: Resp())
    out = json.loads(fx.convert_price.invoke({"currency": "vnd", "product_ids": ["LP076"]}))
    assert out["rate_status"] == "live" and out["items"][0]["price_vnd"] == 439 * 25000

    def boom(*a, **k): raise httpx.ConnectError("down")
    fx._cache.update(rates=None, fetched_at=0.0)
    monkeypatch.setattr(httpx, "get", boom)
    out = json.loads(fx.convert_price.invoke({"currency": "EUR", "amounts_usd": [100]}))
    assert out["rate_status"] == "static" and "approximate" in out["note"]
    assert "error" in json.loads(fx.convert_price.invoke({"currency": "XYZ", "amounts_usd": [1]}))
