import uuid
from datetime import datetime, timezone

from botocore.exceptions import ClientError

from app import db
from app.models import TransferRequest

# A user cannot send more than 500.00 in total per UTC day.
DAILY_LIMIT_CENTS = 50_000


def _now() -> datetime:
    # One place for the clock, so tests can move it across midnight UTC.
    return datetime.now(timezone.utc)


class TransferError(Exception):
    def __init__(self, status_code: int, code: str):
        super().__init__(code)
        self.status_code = status_code
        self.code = code


def format_cents(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def get_balance(user_id: str) -> int:
    # Always read the balance from DynamoDB with a strongly consistent read. A cached balance can
    # be stale (the receiver's entry was never cleared, and a read racing a transfer can put an old
    # value back), and the ticket requires the current balance, right after a transfer too.
    account = db.table(db.ACCOUNTS).get_item(Key={"user_id": user_id}, ConsistentRead=True).get("Item")
    if account is None:
        raise TransferError(404, "account_not_found")
    return int(account["balance"])


def _previous_transfer(key: str) -> dict | None:
    previous = db.table(db.IDEMPOTENCY).get_item(Key={"idempotency_key": key}, ConsistentRead=True).get("Item")
    if previous is None:
        return None
    return db.table(db.TRANSFERS).get_item(Key={"transfer_id": previous["transfer_id"]}, ConsistentRead=True)["Item"]


def send_money(sender_id: str, request: TransferRequest, idempotency_key: str) -> dict:
    key = f"{sender_id}#{idempotency_key}"
    previous = _previous_transfer(key)
    if previous:
        return previous

    if request.to_user_id == sender_id:
        raise TransferError(422, "cannot_send_to_yourself")

    # Exact: amount is a Decimal with at most 2 decimal places, so this never needs rounding.
    amount_cents = int(request.amount * 100)
    # A single transfer over the limit can never succeed. This only looks at the request, so it
    # cannot race; the running total for the day is checked inside the transaction below.
    if amount_cents > DAILY_LIMIT_CENTS:
        raise TransferError(409, "daily_limit_exceeded")

    accounts = db.table(db.ACCOUNTS)
    sender = accounts.get_item(Key={"user_id": sender_id}).get("Item")
    receiver = accounts.get_item(Key={"user_id": request.to_user_id}).get("Item")
    if sender is None or receiver is None:
        raise TransferError(404, "account_not_found")

    if sender["balance"] < amount_cents:
        raise TransferError(409, "insufficient_funds")

    now = _now()
    transfer = {
        "transfer_id": str(uuid.uuid4()),
        "from_user_id": sender_id,
        "to_user_id": request.to_user_id,
        "amount_cents": amount_cents,
        "created_at": now.isoformat(),
    }
    # The UTC day comes from the same timestamp as created_at, so a transfer always counts
    # towards the day it is recorded on.
    daily_total_id = f"{sender_id}#{now.date().isoformat()}"

    # db.client() comes from the boto3 resource, so it converts plain Python values for us.
    # All writes happen in one transaction: either the key is claimed, the transfer stored and
    # both balances moved, or nothing happens. The conditions are checked by DynamoDB at write
    # time, so they hold across instances:
    #   - the idempotency key is new, so only one request per key can ever commit;
    #   - the sender still has enough money, so parallel sends can never overdraw it;
    #   - the receiver still exists, so the update never creates an account;
    #   - the sender's total for today stays within the daily limit, so parallel sends can never
    #     go over it. The total lives in its own item because a transaction cannot touch the
    #     account item twice, and a new day simply starts a new item at zero.
    # The early checks above only save a round trip; these conditions are the real guard.
    try:
        db.client().transact_write_items(
            TransactItems=[
                {
                    "Put": {
                        "TableName": db.IDEMPOTENCY,
                        "Item": {"idempotency_key": key, "transfer_id": transfer["transfer_id"]},
                        "ConditionExpression": "attribute_not_exists(idempotency_key)",
                    }
                },
                {"Put": {"TableName": db.TRANSFERS, "Item": transfer}},
                {
                    "Update": {
                        "TableName": db.ACCOUNTS,
                        "Key": {"user_id": sender_id},
                        "UpdateExpression": "SET balance = balance - :amount",
                        "ConditionExpression": "balance >= :amount",
                        "ExpressionAttributeValues": {":amount": amount_cents},
                    }
                },
                {
                    "Update": {
                        "TableName": db.ACCOUNTS,
                        "Key": {"user_id": request.to_user_id},
                        "UpdateExpression": "SET balance = balance + :amount",
                        "ConditionExpression": "attribute_exists(user_id)",
                        "ExpressionAttributeValues": {":amount": amount_cents},
                    }
                },
                {
                    "Update": {
                        "TableName": db.DAILY_TOTALS,
                        "Key": {"total_id": daily_total_id},
                        "UpdateExpression": "SET total_cents = if_not_exists(total_cents, :zero) + :amount",
                        # total + amount <= limit, written so DynamoDB compares a stored value to a number.
                        # No item yet means nothing sent today; the early check covers amount > limit.
                        "ConditionExpression": "attribute_not_exists(total_cents) OR total_cents <= :max_before",
                        "ExpressionAttributeValues": {
                            ":zero": 0,
                            ":amount": amount_cents,
                            ":max_before": DAILY_LIMIT_CENTS - amount_cents,
                        },
                    }
                },
            ]
        )
    except ClientError as error:
        if error.response["Error"]["Code"] != "TransactionCanceledException":
            raise
        # One reason per transaction item, in the order above.
        failed = [reason.get("Code") for reason in error.response.get("CancellationReasons", [])]
        key_taken, _, sender_failed, receiver_failed, daily_total_failed = (failed + [None] * 5)[:5]

        # Another request with the same key got there first: return its transfer. Checked first,
        # because a retry whose original already spent the money must still get that transfer back.
        if key_taken == "ConditionalCheckFailed":
            previous = _previous_transfer(key)
            if previous:
                return previous
        if sender_failed == "ConditionalCheckFailed":
            raise TransferError(409, "insufficient_funds") from error
        if receiver_failed == "ConditionalCheckFailed":
            raise TransferError(404, "account_not_found") from error
        if daily_total_failed == "ConditionalCheckFailed":
            raise TransferError(409, "daily_limit_exceeded") from error
        # DynamoDB can also cancel us because a concurrent transaction on the same items has not
        # committed yet. Nothing was written, so the client can safely retry with the same key.
        if "TransactionConflict" in failed:
            raise TransferError(409, "transfer_in_progress") from error
        raise

    return transfer
