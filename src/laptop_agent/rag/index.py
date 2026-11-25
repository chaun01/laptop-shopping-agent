"""Build the knowledge base: products, reviews and policy chunks -> Qdrant (embedded mode).

One collection `kb` holds every document; `doc_type` in the payload separates them so that
retrieval can use metadata filters (doc_type, category, brand, price, battery, weight ...).

Usage: python -m laptop_agent.rag.index
"""
import json
import re
from pathlib import Path

from qdrant_client import QdrantClient, models

from laptop_agent.config import ROOT, get_settings
from laptop_agent.db.database import connect, rows
from laptop_agent.llm import get_embeddings

COLLECTION = "kb"
DOCS_CACHE = ROOT / "data" / "processed" / "kb_docs.json"   # same corpus is used by BM25


def chunk_policies(policy_dir: Path) -> list[dict]:
    """Split each policy file on '## ' headings; keep the document title as context."""
    docs = []
    for f in sorted(policy_dir.glob("*.md")):
        text = f.read_text()
        title = text.splitlines()[0].lstrip("# ").strip()
        for section in re.split(r"\n(?=## )", text)[1:]:
            heading = section.splitlines()[0].lstrip("# ").strip()
            body = section.split("\n", 1)[1].strip() if "\n" in section else ""
            docs.append({"doc_type": "policy", "source": f.name, "section": heading,
                         "text": f"{title} - {heading}: {body}"})
    return docs


def build_corpus() -> list[dict]:
    docs: list[dict] = []
    with connect() as conn:
        for p in rows(conn.execute("SELECT * FROM products")):
            docs.append({"doc_type": "product", "product_id": p["id"], "text": p["description"],
                         **{k: p[k] for k in ("name", "brand", "category", "price_usd", "ram_gb",
                                              "storage_gb", "weight_kg", "battery_hours", "screen_inch",
                                              "gpu", "os", "stock")}})
        for r in rows(conn.execute(
                "SELECT r.*, p.name FROM reviews r JOIN products p ON p.id = r.product_id")):
            docs.append({"doc_type": "review", "product_id": r["product_id"], "review_id": r["id"],
                         "rating": r["rating"], "name": r["name"], "text": r["text"]})
    docs += chunk_policies(ROOT / "data" / "policies")
    return docs


def get_client() -> QdrantClient:
    return QdrantClient(path=str(get_settings().qdrant_path))


def main() -> None:
    docs = build_corpus()
    vectors = get_embeddings().embed_documents([d["text"] for d in docs], chunk_size=500)
    client = get_client()
    if client.collection_exists(COLLECTION):
        client.delete_collection(COLLECTION)
    client.create_collection(COLLECTION, vectors_config=models.VectorParams(
        size=len(vectors[0]), distance=models.Distance.COSINE))
    client.upsert(COLLECTION, points=[models.PointStruct(id=i, vector=v, payload=d)
                                      for i, (d, v) in enumerate(zip(docs, vectors))])
    DOCS_CACHE.write_text(json.dumps(docs))
    counts = {}
    for d in docs:
        counts[d["doc_type"]] = counts.get(d["doc_type"], 0) + 1
    print(f"Indexed {len(docs)} docs into '{COLLECTION}': {counts}")
    client.close()


if __name__ == "__main__":
    main()
