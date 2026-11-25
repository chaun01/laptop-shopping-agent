"""External API tool: live exchange rates (open.er-api.com, free, no key) to quote prices in the
customer's currency.

Reliability: 5s timeout, 1h in-process cache, and a stale-cache / static fallback so an outage of
the external API degrades the answer ("approximate rate") instead of breaking the turn.
"""
import json
import time

import httpx
from langchain_core.tools import tool

from laptop_agent.db.database import connect, get_products

FX_URL = "https://open.er-api.com/v6/latest/USD"
CACHE_TTL_S = 3600
SUPPORTED = ("VND", "EUR", "GBP", "JPY", "SGD", "AUD", "THB", "CNY", "KRW", "INR")
# last-resort rates (approximate) if the API was never reachable in this process
STATIC_RATES = {"VND": 25700, "EUR": 0.91, "GBP": 0.78, "JPY": 158, "SGD": 1.29, "AUD": 1.52,
                "THB": 35.5, "CNY": 7.2, "KRW": 1390, "INR": 84}

_cache: dict = {"rates": None, "fetched_at": 0.0, "source_time": None}


def fetch_rates() -> tuple[dict, str]:
    """Return (rates, status) where status is live | cached | stale | static."""
    now = time.time()
    if _cache["rates"] and now - _cache["fetched_at"] < CACHE_TTL_S:
        return _cache["rates"], "cached"
    try:
        r = httpx.get(FX_URL, timeout=5)
        r.raise_for_status()
        data = r.json()
        if data.get("result") != "success":
            raise ValueError("fx api returned non-success")
        _cache.update(rates=data["rates"], fetched_at=now, source_time=data.get("time_last_update_utc"))
        return data["rates"], "live"
    except Exception:
        if _cache["rates"]:
            return _cache["rates"], "stale"
        return STATIC_RATES, "static"


@tool
def convert_price(currency: str, product_ids: list[str] | None = None,
                  amounts_usd: list[float] | None = None) -> str:
    """Convert laptop prices (by product id) or USD amounts (e.g. an order total) into another currency
    such as VND or EUR, using live exchange rates. Store prices are set in USD; the result is an
    estimate for the customer's information."""
    currency = currency.upper().strip()
    if currency not in SUPPORTED:
        return json.dumps({"error": f"unsupported currency; supported: {list(SUPPORTED)}"})
    rates, status = fetch_rates()
    rate = rates.get(currency) or STATIC_RATES[currency]
    items = []
    if product_ids:
        with connect() as conn:
            for p in get_products(conn, product_ids[:5]):
                items.append({"id": p["id"], "name": p["name"], "price_usd": p["price_usd"]})
    for a in (amounts_usd or [])[:5]:
        items.append({"price_usd": a})
    if not items:
        return json.dumps({"error": "give product_ids or amounts_usd"})
    for it in items:
        it[f"price_{currency.lower()}"] = round(it["price_usd"] * rate, 0 if rate > 50 else 2)
    out = {"currency": currency, "rate_per_usd": rate, "rate_status": status,
           "rate_time": _cache.get("source_time"), "items": items,
           "note": "Charged in USD; converted amount is an estimate."}
    if status in ("stale", "static"):
        out["note"] += " Live rates unavailable - approximate rate used, tell the customer."
    return json.dumps(out)
