"""Shared helpers for the eval scripts: dataset loading, spec-constraint checking, stats."""
import json
import re
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
DATASETS = ROOT / "evals" / "datasets"
REPORTS = ROOT / "evals" / "reports"
PRODUCT_ID_RE = re.compile(r"\bLP\d{3}\b")


def load_jsonl(name: str) -> list[dict]:
    return [json.loads(line) for line in (DATASETS / name).read_text().splitlines() if line.strip()]


def satisfies(p: dict, c: dict) -> bool:
    """Ground truth relevance: a product is relevant iff it meets every spec constraint."""
    checks = {
        "max_price": lambda v: p["price_usd"] <= v,
        "min_price": lambda v: p["price_usd"] >= v,
        "category": lambda v: p["category"] == v,
        "brand": lambda v: p["brand"] == v,
        "os": lambda v: p["os"] == v,
        "panel": lambda v: p["panel"] == v,
        "gpu": lambda v: p["gpu"] == v,
        "cpu_contains": lambda v: v in p["cpu"],
        "min_ram_gb": lambda v: p["ram_gb"] >= v,
        "min_storage_gb": lambda v: p["storage_gb"] >= v,
        "max_weight_kg": lambda v: p["weight_kg"] <= v,
        "min_battery_hours": lambda v: p["battery_hours"] >= v,
        "min_screen_inch": lambda v: p["screen_inch"] >= v,
        "max_screen_inch": lambda v: p["screen_inch"] <= v,
        "min_refresh_hz": lambda v: p["refresh_hz"] >= v,
        "dedicated_gpu": lambda v: (p["gpu"] != "Integrated") == v,
        "in_stock": lambda v: (p["stock"] > 0) == v,
    }
    return all(checks[k](v) for k, v in c.items())


def all_products() -> dict[str, dict]:
    from laptop_agent.db.database import connect, rows
    with connect() as conn:
        return {p["id"]: p for p in rows(conn.execute("SELECT * FROM products"))}


def pct(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    return round(s[min(len(s) - 1, int(round(q * (len(s) - 1))))], 2)


def mean(values: list[float]) -> float:
    return round(statistics.mean(values), 3) if values else 0.0
