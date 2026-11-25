"""Create data/shop.db from data/processed/*.json and seed demo users + one past order.

Usage: python scripts/load_db.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from laptop_agent.config import get_settings  # noqa: E402
from laptop_agent.db.database import connect, init_db  # noqa: E402

PRODUCT_COLS = ["id", "name", "brand", "series", "category", "cpu", "gpu", "ram_gb", "storage_gb",
                "screen_inch", "resolution", "panel", "refresh_hz", "weight_kg", "battery_hours", "os",
                "price_usd", "stock", "release_year", "description"]


def main() -> None:
    db_path = get_settings().db_path
    db_path.unlink(missing_ok=True)
    products = json.loads((ROOT / "data/processed/products.json").read_text())
    reviews = json.loads((ROOT / "data/processed/reviews.json").read_text())

    with connect(db_path) as conn:
        init_db(conn)
        conn.executemany(
            f"INSERT INTO products ({','.join(PRODUCT_COLS)}) VALUES ({','.join('?' * len(PRODUCT_COLS))})",
            [[p[c] for c in PRODUCT_COLS] for p in products])
        conn.executemany("INSERT INTO reviews (id, product_id, rating, text) VALUES (?,?,?,?)",
                         [(r["id"], r["product_id"], r["rating"], r["text"]) for r in reviews])
        conn.executemany("INSERT INTO users (id, name, email, preferences) VALUES (?,?,?,?)", [
            ("u001", "Alex Demo", "alex@example.com", json.dumps({"budget_usd": 1000, "use_case": "student"})),
            ("u002", "Sam Demo", "sam@example.com", "{}"),
        ])
        p = products[0]
        conn.execute("INSERT INTO orders (id, user_id, status, total_usd, shipping_option) VALUES (?,?,?,?,?)",
                     ("ORD-1001", "u001", "shipped", p["price_usd"], "standard"))
        conn.execute("INSERT INTO order_items VALUES (?,?,?,?)", ("ORD-1001", p["id"], 1, p["price_usd"]))

        n_p = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        n_r = conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
        n_oos = conn.execute("SELECT COUNT(*) FROM products WHERE stock = 0").fetchone()[0]
    print(f"Loaded {db_path.name}: products={n_p} reviews={n_r} out_of_stock={n_oos} users=2 orders=1")


if __name__ == "__main__":
    main()
