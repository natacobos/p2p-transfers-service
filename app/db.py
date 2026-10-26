import os
import threading
import time

import boto3

ACCOUNTS = "accounts"
TRANSFERS = "transfers"
IDEMPOTENCY = "idempotency_keys"

# Table name -> partition key
TABLES = {
    ACCOUNTS: "user_id",
    TRANSFERS: "transfer_id",
    IDEMPOTENCY: "idempotency_key",
}

# Demo users and their starting balances, in cents.
DEMO_BALANCES = {"alice": 100000, "bob": 50000, "carol": 10000}

_local = threading.local()


def resource():
    # boto3 resources are not thread-safe, so each thread gets its own.
    if not hasattr(_local, "resource"):
        session = boto3.session.Session()
        _local.resource = session.resource(
            "dynamodb",
            endpoint_url=os.getenv("DYNAMODB_URL", "http://localhost:8000"),
            region_name=os.getenv("AWS_REGION", "us-east-1"),
        )
    return _local.resource


def client():
    return resource().meta.client


def table(name: str):
    return resource().Table(name)


def wait_until_ready(timeout: float = 30) -> None:
    deadline = time.time() + timeout
    while True:
        try:
            client().list_tables()
            return
        except Exception:
            if time.time() > deadline:
                raise
            time.sleep(0.5)


def create_tables() -> None:
    existing = set(client().list_tables()["TableNames"])
    for name, key in TABLES.items():
        if name in existing:
            continue
        client().create_table(
            TableName=name,
            KeySchema=[{"AttributeName": key, "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": key, "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )


def delete_tables() -> None:
    existing = set(client().list_tables()["TableNames"])
    for name in TABLES:
        if name in existing:
            client().delete_table(TableName=name)


def seed(balances: dict[str, int] = DEMO_BALANCES) -> None:
    for user_id, cents in balances.items():
        table(ACCOUNTS).put_item(Item={"user_id": user_id, "balance": cents})


def setup_demo_data() -> None:
    wait_until_ready()
    create_tables()
    if table(ACCOUNTS).scan(Limit=1)["Count"] == 0:
        seed()
