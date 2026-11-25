"""Catalog / knowledge tools: RAG over products, reviews, policies + SQL for exact specs.

Rule of thumb used by the agent prompt: retrieval finds *candidates*, SQL is the source of
truth for *numbers* (price, stock, specs) - so the agent never quotes a price from memory.
"""
import json
from typing import Literal

from langchain_core.tools import tool

from laptop_agent.config import get_settings
from laptop_agent.db.database import connect, get_products, get_reviews, rating_summary
from laptop_agent.rag.retriever import (ProductFilters, retrieve_policies, retrieve_products_v2,
                                        retrieve_reviews)

SPEC_FIELDS = ["id", "name", "brand", "category", "cpu", "gpu", "ram_gb", "storage_gb", "screen_inch",
               "resolution", "panel", "refresh_hz", "weight_kg", "battery_hours", "os", "price_usd", "stock"]


def _card(p: dict) -> dict:
    return {k: p[k] for k in SPEC_FIELDS if k in p}


@tool
def search_products(
    query: str,
    max_price: float | None = None,
    category: Literal["student", "ultrabook", "business", "gaming", "creator", "2-in-1"] | None = None,
    brand: str | None = None,
    min_ram_gb: int | None = None,
    max_weight_kg: float | None = None,
    min_battery_hours: float | None = None,
    dedicated_gpu: bool | None = None,
    in_stock_only: bool = False,
    k: int = 5,
) -> str:
    """Find laptops matching the customer's needs. `query` = the need in natural language
    (e.g. 'light laptop with long battery for university'). Add explicit filters only for
    constraints the customer stated. Returns up to k candidates with key specs."""
    filters = ProductFilters(max_price=max_price, category=category, brand=brand, min_ram_gb=min_ram_gb,
                             max_weight_kg=max_weight_kg, min_battery_hours=min_battery_hours,
                             dedicated_gpu=dedicated_gpu, in_stock_only=in_stock_only)
    s = get_settings()
    has_filters = any(v not in (None, False) for v in filters.model_dump().values())
    rewrite = s.rag_rewrite == "always" or (s.rag_rewrite == "auto" and not has_filters)
    hits, plan, relaxed = retrieve_products_v2(query, k=min(k, 8), filters=filters,
                                               rewrite=rewrite, rerank=s.rag_rerank)
    with connect() as conn:   # re-read from SQL so prices/stock are always current
        fresh = {p["id"]: p for p in get_products(conn, [h["product_id"] for h in hits])}
        results = [{**_card(fresh[h["product_id"]]), **rating_summary(conn, h["product_id"])}
                   for h in hits if h["product_id"] in fresh]
    out = {"results": results, "applied_filters": plan.filters.model_dump(exclude_none=True)}
    if relaxed:
        out["note"] = f"No exact match; relaxed these preferences: {relaxed}. Tell the customer."
    if not results:
        out["note"] = "No laptops match the hard constraints (budget/brand/OS). Tell the customer."
    return json.dumps(out)


@tool
def get_product_details(product_ids: list[str]) -> str:
    """Get full, authoritative specs, price, stock and rating for 1-5 product ids (e.g. ['LP012'])."""
    with connect() as conn:
        found = get_products(conn, product_ids[:5])
        out = [{**_card(p), **rating_summary(conn, p["id"])} for p in found]
    missing = sorted(set(product_ids[:5]) - {p["id"] for p in out})
    return json.dumps({"products": out, "not_found": missing})


@tool
def compare_products(product_ids: list[str]) -> str:
    """Compare 2-4 laptops side by side and report which one wins on price, weight, battery, RAM."""
    if not 2 <= len(product_ids) <= 4:
        return json.dumps({"error": "compare_products needs 2 to 4 product ids"})
    with connect() as conn:
        ps = [{**_card(p), **rating_summary(conn, p["id"])} for p in get_products(conn, product_ids)]
    if len(ps) < 2:
        return json.dumps({"error": "fewer than 2 valid product ids", "found": [p["id"] for p in ps]})
    winners = {
        "cheapest": min(ps, key=lambda p: p["price_usd"])["id"],
        "lightest": min(ps, key=lambda p: p["weight_kg"])["id"],
        "longest_battery": max(ps, key=lambda p: p["battery_hours"])["id"],
        "most_ram": max(ps, key=lambda p: p["ram_gb"])["id"],
        "best_rated": max(ps, key=lambda p: p["avg_rating"] or 0)["id"],
    }
    return json.dumps({"products": ps, "winners": winners})


@tool
def search_reviews(product_id: str, aspect: str) -> str:
    """Find what customers say about one aspect (e.g. 'battery life', 'heat', 'keyboard') of a laptop."""
    with connect() as conn:
        summary = rating_summary(conn, product_id)
        if summary["review_count"] == 0:
            return json.dumps({"error": f"no reviews for {product_id}"})
        all_reviews = get_reviews(conn, product_id)
    top = retrieve_reviews(product_id, aspect) or all_reviews[:3]
    return json.dumps({"product_id": product_id, **summary,
                       "relevant_reviews": [{"rating": r["rating"], "text": r["text"]} for r in top]})


@tool
def search_policies(question: str) -> str:
    """Search store policies: warranty, returns/refunds, shipping, payment, installments, discounts.
    Always cite the returned `source` when answering."""
    hits = retrieve_policies(question)
    return json.dumps([{"source": f"{h['source']}#{h['section']}", "text": h["text"]} for h in hits])


@tool
def check_stock_price(product_id: str) -> str:
    """Get the live price and stock level of one laptop."""
    with connect() as conn:
        p = get_products(conn, [product_id])
    if not p:
        return json.dumps({"error": f"product {product_id} does not exist"})
    return json.dumps({"id": p[0]["id"], "name": p[0]["name"], "price_usd": p[0]["price_usd"],
                       "stock": p[0]["stock"], "in_stock": p[0]["stock"] > 0})


CATALOG_TOOLS = [search_products, get_product_details, compare_products, search_reviews,
                 search_policies, check_stock_price]
