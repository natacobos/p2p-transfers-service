from pydantic import BaseModel, Field


class TransferRequest(BaseModel):
    to_user_id: str = Field(min_length=1)
    amount: float = Field(gt=0, description="Amount in dollars, for example 12.50")


class TransferResponse(BaseModel):
    transfer_id: str
    from_user_id: str
    to_user_id: str
    amount: str
    created_at: str


class BalanceResponse(BaseModel):
    user_id: str
    balance: str
