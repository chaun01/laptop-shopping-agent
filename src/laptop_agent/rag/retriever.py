"""Retrieval pipelines.

v1 (baseline): dense vector search only.
v2 (advanced): LLM query rewrite -> metadata filters + hybrid (dense + BM25, fused with RRF)
               -> LLM listwise rerank.
Both are kept so the eval can compare them (see evals/run_retrieval_eval.py).
"""
import atexit
import json
import re
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, Field
from qdrant_client import models
from rank_bm25 import BM25Okapi

from laptop_agent.llm import get_embeddings, get_small_model
from laptop_agent.rag.index import COLLECTION, DOCS_CACHE, get_client

DocType = Literal["product", "review", "policy"]
Category = Literal["student", "ultrabook", "business", "gaming", "creator", "2-in-1"]


# ---------------------------------------------------------------- shared resources
@lru_cache
def _client():
    client = get_client()
    atexit.register(client.close)   # embedded Qdrant holds a file lock; release it cleanly
    return client


@lru_cache
def _bm25(doc_type: str) -> tuple[BM25Okapi, list[dict]]:
    docs = [d for d in json.loads(DOCS_CACHE.read_text()) if d["doc_type"] == doc_type]
    return BM25Okapi([_tokenize(d["text"]) for d in docs]), docs


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _doc_key(d: dict) -> str:
    return d.get("review_id") or d.get("product_id") if d["doc_type"] != "policy" \
        else f"{d['source']}#{d['section']}"


# ---------------------------------------------------------------- metadata filters
class ProductFilters(BaseModel):
    category: Category | None = None
    brand: str | None = Field(None, description="Dell, HP, Lenovo, Asus, Acer, Apple or MSI")
    max_price: float | None = None
    min_price: float | None = None
    min_ram_gb: int | None = None
    max_weight_kg: float | None = None
    min_battery_hours: float | None = None
    dedicated_gpu: bool | None = None
    os: Literal["Windows 11", "macOS"] | None = None
    in_stock_only: bool = False


def _qdrant_filter(doc_type: str, f: ProductFilters | None = None,
                   product_id: str | None = None) -> models.Filter:
    must = [models.FieldCondition(key="doc_type", match=models.MatchValue(value=doc_type))]
    if product_id:
        must.append(models.FieldCondition(key="product_id", match=models.MatchValue(value=product_id)))
    if f:
        for key, val in (("category", f.category), ("brand", f.brand), ("os", f.os)):
            if val:
                must.append(models.FieldCondition(key=key, match=models.MatchValue(value=val)))
        ranges = {"price_usd": (f.min_price, f.max_price), "ram_gb": (f.min_ram_gb, None),
                  "weight_kg": (None, f.max_weight_kg), "battery_hours": (f.min_battery_hours, None)}
        for key, (lo, hi) in ranges.items():
            if lo is not None or hi is not None:
                must.append(models.FieldCondition(key=key, range=models.Range(gte=lo, lte=hi)))
        if f.in_stock_only:
            must.append(models.FieldCondition(key="stock", range=models.Range(gt=0)))
    must_not = []
    if f and f.dedicated_gpu is True:
        must_not.append(models.FieldCondition(key="gpu", match=models.MatchValue(value="Integrated")))
    if f and f.dedicated_gpu is False:
        must.append(models.FieldCondition(key="gpu", match=models.MatchValue(value="Integrated")))
    return models.Filter(must=must, must_not=must_not or None)


def _passes(d: dict, f: ProductFilters | None) -> bool:
    """Same filter applied in Python to BM25 hits (BM25 index has no native filtering)."""
    if not f:
        return True
    checks = [
        f.category is None or d.get("category") == f.category,
        f.brand is None or d.get("brand") == f.brand,
        f.os is None or d.get("os") == f.os,
        f.max_price is None or d["price_usd"] <= f.max_price,
        f.min_price is None or d["price_usd"] >= f.min_price,
        f.min_ram_gb is None or d["ram_gb"] >= f.min_ram_gb,
        f.max_weight_kg is None or d["weight_kg"] <= f.max_weight_kg,
        f.min_battery_hours is None or d["battery_hours"] >= f.min_battery_hours,
        f.dedicated_gpu is None or (d["gpu"] != "Integrated") == f.dedicated_gpu,
        not f.in_stock_only or d["stock"] > 0,
    ]
    return all(checks)


# ---------------------------------------------------------------- retrieval primitives
@lru_cache(maxsize=2048)
def embed_query_cached(text: str) -> tuple[float, ...]:
    """Repeated queries (popular searches, review aspects, eval reruns) skip the embedding API call."""
    return tuple(get_embeddings().embed_query(text))


def warmup() -> None:
    """Open Qdrant, build BM25 indexes and the embedding client once at startup (avoids cold-start spikes)."""
    _client()
    for t in ("product", "review", "policy"):
        _bm25(t)
    embed_query_cached("laptop")


def dense_search(query: str, doc_type: DocType, k: int = 10, filters: ProductFilters | None = None,
                 product_id: str | None = None) -> list[dict]:
    vec = list(embed_query_cached(query))
    hits = _client().query_points(COLLECTION, query=vec, limit=k,
                                  query_filter=_qdrant_filter(doc_type, filters, product_id)).points
    return [{**h.payload, "score": h.score} for h in hits]


def bm25_search(query: str, doc_type: DocType, k: int = 10, filters: ProductFilters | None = None,
                product_id: str | None = None) -> list[dict]:
    bm25, docs = _bm25(doc_type)
    scores = bm25.get_scores(_tokenize(query))
    ranked = sorted(zip(scores, docs), key=lambda x: -x[0])
    out = [{**d, "score": float(s)} for s, d in ranked
           if s > 0 and _passes(d, filters) and (not product_id or d.get("product_id") == product_id)]
    return out[:k]


def rrf_fuse(*result_lists: list[dict], k: int = 60) -> list[dict]:
    """Reciprocal Rank Fusion: robust way to merge rankings with incomparable scores."""
    scores, docs = {}, {}
    for results in result_lists:
        for rank, d in enumerate(results):
            key = _doc_key(d)
            scores[key] = scores.get(key, 0) + 1 / (k + rank + 1)
            docs.setdefault(key, d)
    return [{**docs[key], "score": s} for key, s in sorted(scores.items(), key=lambda x: -x[1])]


# ---------------------------------------------------------------- query rewrite + rerank
class QueryPlan(BaseModel):
    """Search plan extracted from a shopper's request."""
    search_query: str = Field(description="Short keyword-rich query describing desired laptop traits, "
                                          "e.g. 'lightweight long battery life ultrabook OLED'")
    filters: ProductFilters = Field(default_factory=ProductFilters,
                                    description="Only hard constraints the user explicitly stated")


REWRITE_PROMPT = """You turn a laptop shopper's request into a search plan.
Map vague needs to concrete specs:
- "long/all-day battery" -> min_battery_hours 10 ; "light/portable/carry around" -> max_weight_kg 1.4
- "gaming", "play games" -> category gaming and dedicated_gpu true ; "video editing/3D" -> category creator
- "under $X"/"budget X" -> max_price X ; "Mac" -> brand Apple
- Do NOT set category from who the user is ("student", "university", "office") - only from an
  explicitly named laptop type (gaming, ultrabook, business, 2-in-1, creator/workstation).
Only set a filter when the user clearly implies it. Request: {query}"""


@lru_cache(maxsize=1024)
def _rewrite_cached(query: str) -> QueryPlan:
    return get_small_model().with_structured_output(QueryPlan).invoke(REWRITE_PROMPT.format(query=query))


def rewrite_query(query: str) -> QueryPlan:
    try:
        return _rewrite_cached(query).model_copy(deep=True)   # copy: callers mutate the plan
    except Exception:
        return QueryPlan(search_query=query)   # fail open: rewrite is an optimisation, not a requirement


class RerankResult(BaseModel):
    ranked_ids: list[str] = Field(description="Candidate ids, most relevant first")


def llm_rerank(query: str, candidates: list[dict], top_n: int) -> list[dict]:
    if len(candidates) <= 1:
        return candidates
    listing = "\n".join(f"[{_doc_key(c)}] {c['text'][:300]}" for c in candidates)
    prompt = (f"Rank these laptop candidates by how well they satisfy the request.\n"
              f"Request: {query}\n\nCandidates:\n{listing}\n\nReturn the ids, best first.")
    try:
        order = get_small_model().with_structured_output(RerankResult).invoke(prompt).ranked_ids
    except Exception:
        return candidates[:top_n]
    by_key = {_doc_key(c): c for c in candidates}
    ranked = [by_key[i] for i in order if i in by_key]
    ranked += [c for c in candidates if c not in ranked]   # never drop candidates the LLM omitted
    return ranked[:top_n]


# ---------------------------------------------------------------- public pipelines
def retrieve_products_v1(query: str, k: int = 5) -> list[dict]:
    return dense_search(query, "product", k=k)


# When no product matches, soft preferences are dropped step by step. Hard constraints
# (price, brand, OS, stock) are never relaxed, so results never violate the user's budget.
RELAX_STEPS = [("category",), ("max_weight_kg", "min_battery_hours"), ("min_ram_gb", "dedicated_gpu")]


def retrieve_products_v2(query: str, k: int = 5, filters: ProductFilters | None = None,
                         rewrite: bool = True, rerank: bool = True
                         ) -> tuple[list[dict], QueryPlan, list[str]]:
    """Returns (products, plan, relaxed_filter_names)."""
    plan = rewrite_query(query) if rewrite else QueryPlan(search_query=query)
    if filters:   # explicit filters from the agent's tool call win over the rewrite's guesses
        merged = plan.filters.model_dump() | {k_: v for k_, v in filters.model_dump().items()
                                              if v not in (None, False)}
        plan.filters = ProductFilters(**merged)
    q, pool, relaxed = plan.search_query, max(k * 3, 15), []
    active = plan.filters.model_copy()
    for step in [()] + RELAX_STEPS:
        for name in step:
            if getattr(active, name) is not None:
                relaxed.append(name)
            setattr(active, name, None)
        candidates = rrf_fuse(dense_search(q, "product", pool, active),
                              bm25_search(q, "product", pool, active))[:pool]
        if candidates:
            break
    results = llm_rerank(query, candidates, k) if rerank else candidates[:k]
    return results, plan, relaxed


def retrieve_reviews(product_id: str, aspect: str, k: int = 3) -> list[dict]:
    return rrf_fuse(dense_search(aspect, "review", k * 2, product_id=product_id),
                    bm25_search(aspect, "review", k * 2, product_id=product_id))[:k]


def retrieve_policies(question: str, k: int = 3) -> list[dict]:
    return rrf_fuse(dense_search(question, "policy", k * 2), bm25_search(question, "policy", k * 2))[:k]
