import pytest
from fastapi import HTTPException

from laptop_agent.api import main


def test_rate_limit(monkeypatch):
    monkeypatch.setattr(main, "RATE_LIMIT_PER_MIN", 3)
    main._hits.clear()
    for _ in range(3):
        main.rate_limit("u_rl")
    with pytest.raises(HTTPException) as e:
        main.rate_limit("u_rl")
    assert e.value.status_code == 429
    main.rate_limit("other_user")   # limits are per user


def test_customer_profile(temp_db):
    from fastapi.testclient import TestClient

    client = TestClient(main.app)          # no `with`: lifespan (LLM warm-up) is not started
    r = client.get("/customers/u001/profile")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "Alex Demo" and body["order_count"] == 1 and body["preferences"]["budget_usd"] == 1000
    assert client.get("/customers/nobody/profile").status_code == 404
    assert client.get("/customers/bad id/profile").status_code == 422
