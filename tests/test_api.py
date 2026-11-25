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
