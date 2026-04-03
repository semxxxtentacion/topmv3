from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from backend.db.queries import get_user_balance, add_user_balance, get_user_by_id
from backend.middleware.auth import get_current_user_id

router = APIRouter(prefix="/balance", tags=["balance"])


class BalanceResponse(BaseModel):
    status: str
    user_id: int
    balance: int


@router.get("/", response_model=BalanceResponse)
async def get_balance(user_id: int = Depends(get_current_user_id)):
    """Получить текущий баланс заявок пользователя."""
    balance = await get_user_balance(user_id)
    if balance is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return BalanceResponse(status="ok", user_id=user_id, balance=balance)
