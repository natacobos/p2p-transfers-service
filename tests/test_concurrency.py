import threading
from concurrent.futures import ThreadPoolExecutor

from app import db, transfers
from app.models import TransferRequest
from tests.conftest import balance

PARALLEL_REQUESTS = 10


def send_in_parallel(calls):
    """Run send_money calls at the same moment, like several instances handling retries at once.

    Each thread opens its DynamoDB connection before the barrier: creating a boto3 session is
    slow, and otherwise the first thread finishes its transfer before the others start, which
    hides the race.
    """
    barrier = threading.Barrier(len(calls))

    def fire(call):
        sender_id, to_user_id, amount, key = call
        db.table(db.ACCOUNTS).get_item(Key={"user_id": sender_id})  # warm up this thread
        barrier.wait()
        try:
            return transfers.send_money(sender_id, TransferRequest(to_user_id=to_user_id, amount=amount), key)
        except transfers.TransferError as error:
            return error

    with ThreadPoolExecutor(max_workers=len(calls)) as pool:
        return list(pool.map(fire, calls))


def test_concurrent_retries_with_same_key_create_a_single_transfer(client):
    results = send_in_parallel([("alice", "bob", 10, "same-key")] * PARALLEL_REQUESTS)

    assert all(isinstance(r, dict) for r in results), results
    transfer_ids = {r["transfer_id"] for r in results}
    assert len(transfer_ids) == 1, f"expected 1 transfer, got {len(transfer_ids)}"
    assert db.table(db.TRANSFERS).scan(ConsistentRead=True)["Count"] == 1
    assert balance(client, "alice") == "990.00"
    assert balance(client, "bob") == "510.00"


def test_parallel_sends_cannot_overdraw_the_balance(client):
    # carol has 100.00 and sends 80.00 from two devices at once (different keys).
    results = send_in_parallel([("carol", "bob", 80, "phone"), ("carol", "bob", 80, "laptop")])

    succeeded = [r for r in results if isinstance(r, dict)]
    rejected = [r for r in results if isinstance(r, transfers.TransferError)]
    assert len(succeeded) == 1, results
    assert len(rejected) == 1 and rejected[0].code == "insufficient_funds", results
    assert balance(client, "carol") == "20.00"
    assert balance(client, "bob") == "580.00"
