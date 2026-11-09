from decimal import Decimal

from pydantic import BaseModel, Field


class TransferRequest(BaseModel):
    to_user_id: str = Field(min_length=1)
    # Decimal, not float: pydantic builds it from the JSON text, so 19.99 stays exactly 19.99.
    # More than 2 decimal places is rejected rather than silently rounded.
    amount: Decimal = Field(gt=0, decimal_places=2, description="Amount in dollars, for example 12.50")


class TransferResponse(BaseModel):
    transfer_id: str
    from_user_id: str
    to_user_id: str
    amount: str
    created_at: str


class BalanceResponse(BaseModel):
    user_id: str
    balance: str
