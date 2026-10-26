import uuid
from datetime import datetime, timezone

from app import cache, db
from app.models import TransferRequest


class TransferError(Exception):
    def __init__(self, status_code: int, code: str):
        super().__init__(code)
        self.status_code = status_code
        self.code = code


def format_cents(cents: int) -> str:
    return f"{cents // 100}.{cents % 100:02d}"


def get_balance(user_id: str) -> int:
    cached = cache.get_balance(user_id)
    if cached is not None:
        return cached

    account = db.table(db.ACCOUNTS).get_item(Key={"user_id": user_id}).get("Item")
    if account is None:
        raise TransferError(404, "account_not_found")

    balance = int(account["balance"])
    cache.set_balance(user_id, balance)
    return balance


def send_money(sender_id: str, request: TransferRequest, idempotency_key: str) -> dict:
    key = f"{sender_id}#{idempotency_key}"
    previous = db.table(db.IDEMPOTENCY).get_item(Key={"idempotency_key": key}).get("Item")
    if previous:
        return db.table(db.TRANSFERS).get_item(Key={"transfer_id": previous["transfer_id"]})["Item"]

    if request.to_user_id == sender_id:
        raise TransferError(422, "cannot_send_to_yourself")

    amount_cents = int(request.amount * 100)

    accounts = db.table(db.ACCOUNTS)
    sender = accounts.get_item(Key={"user_id": sender_id}).get("Item")
    receiver = accounts.get_item(Key={"user_id": request.to_user_id}).get("Item")
    if sender is None or receiver is None:
        raise TransferError(404, "account_not_found")

    if sender["balance"] < amount_cents:
        raise TransferError(409, "insufficient_funds")

    accounts.update_item(
        Key={"user_id": sender_id},
        UpdateExpression="SET balance = :balance",
        ExpressionAttributeValues={":balance": sender["balance"] - amount_cents},
    )
    accounts.update_item(
        Key={"user_id": request.to_user_id},
        UpdateExpression="SET balance = :balance",
        ExpressionAttributeValues={":balance": receiver["balance"] + amount_cents},
    )

    transfer = {
        "transfer_id": str(uuid.uuid4()),
        "from_user_id": sender_id,
        "to_user_id": request.to_user_id,
        "amount_cents": amount_cents,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    db.table(db.TRANSFERS).put_item(Item=transfer)
    db.table(db.IDEMPOTENCY).put_item(Item={"idempotency_key": key, "transfer_id": transfer["transfer_id"]})

    cache.delete_balance(sender_id)
    return transfer
