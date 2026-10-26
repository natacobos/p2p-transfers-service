import os

import redis

BALANCE_TTL_SECONDS = 300

_client = redis.Redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/0"))


def client() -> redis.Redis:
    return _client


def _key(user_id: str) -> str:
    return f"balance:{user_id}"


def get_balance(user_id: str) -> int | None:
    value = _client.get(_key(user_id))
    return int(value) if value is not None else None


def set_balance(user_id: str, cents: int) -> None:
    _client.set(_key(user_id), cents, ex=BALANCE_TTL_SECONDS)


def delete_balance(user_id: str) -> None:
    _client.delete(_key(user_id))
