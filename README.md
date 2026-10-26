# Code Challenge — P2P transfers (30 minutes)

## The situation

This small Python service lets users send money to each other. It uses FastAPI, DynamoDB (DynamoDB Local here) and Redis as a cache. It implements ticket **PAY-417** below and went live last week. The tests pass, but support has received these reports from users:

- "I tapped Send once on a bad connection, and the money was sent several times."
- "I had 100.00 and sent 80.00 from my phone and my laptop at the same time. Both went through."
- "A friend sent me money, but my balance did not change for several minutes."
- "I sent 19.99, and my friend received 19.98."

Your job is to find the cause of each report in the code, fix it, and then extend the service.

You may use your usual tools, including an AI assistant. Please share your screen and explain what you ask it and how you check what it gives you.

## Ticket PAY-417 — Send money to another user

A signed-in user sends money from their account to another user's account. The service runs as several instances at the same time, and mobile clients retry requests when the network fails.

**Acceptance criteria**

1. A user can send an amount to another existing user. The sender's balance goes down and the receiver's balance goes up by that amount.
2. A user can never send more money than they have. The sender's balance can never go negative.
3. Retrying a request with the same `Idempotency-Key` never creates a second transfer, even if the retries arrive at the same time. The retry gets the original transfer back.
4. The balance endpoint always shows the current balance, including right after a transfer.
5. Amounts are exact to the cent. Sending 19.99 moves exactly 19.99.
6. A user can only send money from their own account.

## Steps

1. **Investigate (10 minutes).** For each report, find the cause in the code and the acceptance criterion it breaks. Reproduce it if you can. Tell us what you would fix first. Do not change code yet.
2. **Fix (12 minutes).** Fix the causes you found. Show how you verified each fix, with a test where you can.
3. **Extend (8 minutes).** A new acceptance criterion is added to the ticket:

   > 7. A user cannot send more than 500.00 in total per day (UTC). This holds even when several requests arrive at the same time.

   Implement it, with a test. If time is short, explain how you would finish it.

## Rules

- Keep the existing code; do not rewrite it from scratch.
- Check the code against the ticket; do not assume it is correct because the tests pass.
- If you use an AI assistant, review every change it proposes before accepting it, and be ready to explain it.
- Do not add new libraries.

## Running the project

**With Docker (recommended).** You only need Docker Desktop. Clone the repository and run, from its folder:

```bash
docker compose up                                # API on http://localhost:8080 (interactive docs: /docs)
docker compose --profile tests run --rm tests    # run the tests
```

Edit the files in your usual editor; the API reloads when you save. The first start downloads about 320 MB and takes about a minute.

Try it:

```bash
curl -X POST http://localhost:8080/transfers \
  -H "X-User-Id: alice" -H "Idempotency-Key: try-1" -H "Content-Type: application/json" \
  -d '{"to_user_id": "bob", "amount": 12.50}'
curl http://localhost:8080/accounts/bob/balance
```

**Without Docker for Python.** With Python 3.12 installed, keep DynamoDB Local and Redis in Docker and run the rest locally:

```bash
docker compose up -d dynamodb redis
python -m venv .venv && source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt
AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local uvicorn app.main:app --reload --port 8080
AWS_ACCESS_KEY_ID=local AWS_SECRET_ACCESS_KEY=local pytest
```

The repository also works in a GitHub Codespace (Code → Codespaces), which installs everything on its own; then use the Docker commands above.

## Demo data

Users `alice` (1,000.00), `bob` (500.00) and `carol` (100.00). The tests reset this data before each test.

## Files

- `app/main.py`: the API endpoints and the demo authentication (the caller's user id comes in the `X-User-Id` header; it stands in for real authentication).
- `app/transfers.py`: the transfer and balance logic.
- `app/models.py`: request and response models.
- `app/db.py`: DynamoDB tables and demo data. Balances are stored in cents.
- `app/cache.py`: the Redis balance cache.
- `tests/`: the existing tests.
- `compose.yaml`: runs the API, DynamoDB Local, Redis and the tests in Docker.

Think out loud as you work. We are interested in how you reason, not only in the final code.
