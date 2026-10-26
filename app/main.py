from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse

from app import db, transfers
from app.models import BalanceResponse, TransferRequest, TransferResponse


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.setup_demo_data()
    yield


app = FastAPI(title="P2P transfers service", lifespan=lifespan)


@app.exception_handler(transfers.TransferError)
def transfer_error_handler(request, exc: transfers.TransferError):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.code})


def current_user(x_user_id: str | None = Header(default=None)) -> str:
    # Demo authentication: the caller says who they are in the X-User-Id header.
    if not x_user_id:
        raise HTTPException(status_code=401, detail="missing X-User-Id header")
    return x_user_id


def to_response(transfer: dict) -> TransferResponse:
    return TransferResponse(
        transfer_id=transfer["transfer_id"],
        from_user_id=transfer["from_user_id"],
        to_user_id=transfer["to_user_id"],
        amount=transfers.format_cents(int(transfer["amount_cents"])),
        created_at=transfer["created_at"],
    )


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/transfers", status_code=201, response_model=TransferResponse)
def create_transfer(
    request: TransferRequest,
    user_id: str = Depends(current_user),
    idempotency_key: str = Header(min_length=1),
):
    transfer = transfers.send_money(user_id, request, idempotency_key)
    return to_response(transfer)


@app.get("/accounts/{user_id}/balance", response_model=BalanceResponse)
def get_balance(user_id: str):
    cents = transfers.get_balance(user_id)
    return BalanceResponse(user_id=user_id, balance=transfers.format_cents(cents))
