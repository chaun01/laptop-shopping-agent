"""SQLite access layer. All queries are parameterized (no string-built SQL)."""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from laptop_agent.config import get_settings

SCHEMA = Path(__file__).with_name("schema.sql")


@contextmanager
def connect(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(db_path or get_settings().db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA.read_text())


def rows(cur: sqlite3.Cursor) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


# ---------- products ----------
PRODUCT_FILTERS = {
    # filter name -> SQL fragment (values are always bound parameters)
    "category": "category = ?",
    "brand": "brand = ?",
    "min_price": "price_usd >= ?",
    "max_price": "price_usd <= ?",
    "min_ram_gb": "ram_gb >= ?",
    "min_storage_gb": "storage_gb >= ?",
    "max_weight_kg": "weight_kg <= ?",
    "min_battery_hours": "battery_hours >= ?",
    "min_screen_inch": "screen_inch >= ?",
    "max_screen_inch": "screen_inch <= ?",
    "os": "os = ?",
}


def filter_products(conn, filters: dict, in_stock_only: bool = False,
                    sort_by: str = "price_usd", limit: int = 10) -> list[dict]:
    where, params = [], []
    for key, value in filters.items():
        if value is None or key not in PRODUCT_FILTERS:
            continue
        where.append(PRODUCT_FILTERS[key])
        params.append(value)
    if filters.get("dedicated_gpu") is True:
        where.append("gpu != 'Integrated'")
    if in_stock_only:
        where.append("stock > 0")
    sort_col = {"price_usd": "price_usd ASC", "battery_hours": "battery_hours DESC",
                "weight_kg": "weight_kg ASC", "ram_gb": "ram_gb DESC"}.get(sort_by, "price_usd ASC")
    sql = "SELECT * FROM products"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += f" ORDER BY {sort_col} LIMIT ?"
    params.append(int(limit))
    return rows(conn.execute(sql, params))


def get_products(conn, ids: list[str]) -> list[dict]:
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    return rows(conn.execute(f"SELECT * FROM products WHERE id IN ({marks})", ids))


def get_reviews(conn, product_id: str) -> list[dict]:
    return rows(conn.execute("SELECT * FROM reviews WHERE product_id = ?", (product_id,)))


def rating_summary(conn, product_id: str) -> dict:
    r = conn.execute("SELECT COUNT(*) n, ROUND(AVG(rating), 2) avg FROM reviews WHERE product_id = ?",
                     (product_id,)).fetchone()
    return {"review_count": r["n"], "avg_rating": r["avg"]}


# ---------- users / memory ----------
def get_preferences(conn, user_id: str) -> dict:
    r = conn.execute("SELECT preferences FROM users WHERE id = ?", (user_id,)).fetchone()
    return json.loads(r["preferences"]) if r else {}


def save_preferences(conn, user_id: str, prefs: dict) -> None:
    current = get_preferences(conn, user_id)
    current.update({k: v for k, v in prefs.items() if v not in (None, "", [])})
    conn.execute("UPDATE users SET preferences = ? WHERE id = ?", (json.dumps(current), user_id))
