from datetime import datetime, timezone

from app import db, transfers
from tests.conftest import balance, send
from tests.test_concurrency import send_in_parallel


def assert_limit_exceeded(response):
    assert response.status_code == 409
    assert response.json() == {"error": "daily_limit_exceeded"}


def test_can_send_up_to_the_daily_limit_and_no_more(client):
    assert send(client, "alice", "bob", 300, key="a").status_code == 201
    assert send(client, "alice", "bob", 200, key="b").status_code == 201

    assert_limit_exceeded(send(client, "alice", "bob", 0.01, key="c"))
    assert balance(client, "alice") == "500.00"


def test_a_single_transfer_over_the_limit_is_rejected(client):
    assert_limit_exceeded(send(client, "alice", "bob", 500.01))

    assert db.table(db.TRANSFERS).scan(ConsistentRead=True)["Count"] == 0
    assert balance(client, "alice") == "1000.00"


def test_parallel_sends_cannot_exceed_the_daily_limit(client):
    results = send_in_parallel([("alice", "bob", 100, f"key-{i}") for i in range(10)])

    succeeded = [r for r in results if isinstance(r, dict)]
    rejected = [r for r in results if isinstance(r, transfers.TransferError)]
    assert len(succeeded) == 5, results
    assert {r.code for r in rejected} == {"daily_limit_exceeded"}
    assert balance(client, "alice") == "500.00"
    assert balance(client, "bob") == "1000.00"


def test_the_limit_resets_at_midnight_utc(client, monkeypatch):
    monkeypatch.setattr(transfers, "_now", lambda: datetime(2026, 11, 9, 23, 59, tzinfo=timezone.utc))
    assert send(client, "alice", "bob", 500, key="before-midnight").status_code == 201
    assert_limit_exceeded(send(client, "alice", "bob", 0.01, key="same-day"))

    monkeypatch.setattr(transfers, "_now", lambda: datetime(2026, 11, 10, 0, 1, tzinfo=timezone.utc))
    assert send(client, "alice", "bob", 500, key="after-midnight").status_code == 201
    assert balance(client, "alice") == "0.00"


def test_rejected_transfers_do_not_count_towards_the_limit(client):
    # alice has 1000.00: sending 600.00 is within her funds but over the daily limit.
    assert_limit_exceeded(send(client, "alice", "bob", 600, key="too-much"))
    # carol has 100.00: this fails on funds, and must not use up her limit either.
    assert send(client, "carol", "bob", 150, key="no-funds").status_code == 409

    assert send(client, "alice", "bob", 500, key="ok").status_code == 201


def test_a_replayed_transfer_counts_once(client):
    first = send(client, "alice", "bob", 500, key="retry")
    second = send(client, "alice", "bob", 500, key="retry")

    assert first.status_code == 201
    assert second.json()["transfer_id"] == first.json()["transfer_id"]
    assert balance(client, "alice") == "500.00"
