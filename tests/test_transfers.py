import pytest

from app import cache, db
from tests.conftest import balance, send


def test_send_money_moves_the_amount(client):
    response = send(client, "alice", "bob", 25.50)

    assert response.status_code == 201
    body = response.json()
    assert body["from_user_id"] == "alice"
    assert body["to_user_id"] == "bob"
    assert body["amount"] == "25.50"
    assert balance(client, "alice") == "974.50"
    assert balance(client, "bob") == "525.50"


def test_balance_of_a_demo_user(client):
    assert balance(client, "carol") == "100.00"


def test_cannot_send_more_than_the_balance(client):
    response = send(client, "carol", "bob", 150)

    assert response.status_code == 409
    assert response.json() == {"error": "insufficient_funds"}
    assert balance(client, "carol") == "100.00"


def test_retry_with_same_key_returns_the_same_transfer(client):
    first = send(client, "alice", "bob", 10, key="retry-1")
    second = send(client, "alice", "bob", 10, key="retry-1")

    assert first.status_code == 201
    assert second.json()["transfer_id"] == first.json()["transfer_id"]
    assert balance(client, "alice") == "990.00"


def test_unknown_receiver_is_rejected(client):
    response = send(client, "alice", "nobody", 5)

    assert response.status_code == 404


def test_cannot_send_to_yourself(client):
    response = send(client, "alice", "alice", 5)

    assert response.status_code == 422


def test_request_without_user_is_rejected(client):
    response = client.post(
        "/transfers",
        json={"to_user_id": "bob", "amount": 5},
        headers={"Idempotency-Key": "k"},
    )

    assert response.status_code == 401


def test_receiver_sees_the_new_balance_right_after_a_transfer(client):
    assert balance(client, "bob") == "500.00"  # bob checked his balance before the transfer

    send(client, "alice", "bob", 25)

    assert balance(client, "bob") == "525.00"
    assert balance(client, "alice") == "975.00"


def test_balance_comes_from_the_database_not_a_cache(client):
    # A stale value in Redis (from an old read, or a race with a transfer) must never be shown.
    cache.client().set("balance:bob", 1)

    assert balance(client, "bob") == "500.00"


@pytest.mark.parametrize(
    "amount, alice_after, bob_after",
    [
        (19.99, "980.01", "519.99"),
        (0.29, "999.71", "500.29"),
        (1.15, "998.85", "501.15"),
        (4.35, "995.65", "504.35"),
    ],
)
def test_amounts_are_exact_to_the_cent(client, amount, alice_after, bob_after):
    response = send(client, "alice", "bob", amount)

    assert response.status_code == 201
    assert response.json()["amount"] == f"{amount:.2f}"
    assert balance(client, "alice") == alice_after
    assert balance(client, "bob") == bob_after


@pytest.mark.parametrize("amount", [0.001, 19.999, 0])
def test_amounts_that_are_not_whole_cents_are_rejected(client, amount):
    response = send(client, "alice", "bob", amount)

    assert response.status_code == 422
    assert db.table(db.TRANSFERS).scan(ConsistentRead=True)["Count"] == 0
    assert balance(client, "alice") == "1000.00"
