import pytest
from fastapi.testclient import TestClient

from app import cache, db
from app.main import app


@pytest.fixture(autouse=True)
def clean_data():
    db.wait_until_ready()
    db.delete_tables()
    db.create_tables()
    db.seed()
    cache.client().flushdb()
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client


def send(client, sender, to, amount, key="key-1"):
    return client.post(
        "/transfers",
        json={"to_user_id": to, "amount": amount},
        headers={"X-User-Id": sender, "Idempotency-Key": key},
    )


def balance(client, user_id):
    response = client.get(f"/accounts/{user_id}/balance")
    assert response.status_code == 200
    return response.json()["balance"]
