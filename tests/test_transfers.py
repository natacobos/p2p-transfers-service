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
