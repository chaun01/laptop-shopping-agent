from laptop_agent.db.database import connect, filter_products, get_products, rating_summary


def test_filters_respect_constraints():
    with connect() as c:
        res = filter_products(c, {"category": "gaming", "max_price": 1500, "min_ram_gb": 16},
                              in_stock_only=True, limit=50)
    assert res, "expected at least one gaming laptop under $1500"
    for p in res:
        assert p["category"] == "gaming" and p["price_usd"] <= 1500 and p["ram_gb"] >= 16 and p["stock"] > 0


def test_unknown_filter_is_ignored_not_injected():
    with connect() as c:
        res = filter_products(c, {"brand": "Dell' OR '1'='1", "drop_table": "x"}, limit=5)
    assert res == []  # treated as a literal brand value, no SQL injection


def test_get_products_and_ratings():
    with connect() as c:
        p = get_products(c, ["LP001"])[0]
        s = rating_summary(c, "LP001")
    assert p["id"] == "LP001" and s["review_count"] >= 2
