import hashlib
import logging
import datetime
import os
import aiohttp

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel
from dotenv import load_dotenv
from backend.db.queries import set_user_applications_balance, create_payment, get_payment, mark_payment_confirmed
from backend.middleware.auth import get_current_user_id
from backend.config import settings

load_dotenv()
logger = logging.getLogger(__name__)

TARIFFS = {
    "tariff1": {
			"amount": 1500000,
			"requests": 50
		},
    "tariff2": {
			"amount": 3000000,
			"requests": 100
		},
    "tariff3": {
			"amount": 5000000,
			"requests": 250
		},
}

router = APIRouter(prefix="/payment", tags=["payment"])


class RequestInit(BaseModel):
    tariff: str


@router.post('/init')
async def pay_init(
    body: RequestInit,
    user_id: int = Depends(get_current_user_id)
):
    if body.tariff not in TARIFFS:
        raise HTTPException(status_code=422, detail="Invalid tariff")

    amount = TARIFFS[body.tariff]["amount"]

    order_id = f"{user_id}_{int(datetime.datetime.now().timestamp())}"
    description = f"Payment for {body.tariff} tariff"

    payload = {
        "TerminalKey": os.getenv('TINKOFF_TERMINAL'),
        "Amount": amount,
        "OrderId": order_id,
        "Description": description,
        "Password": os.getenv('TINKOFF_PASSWORD'),
    }

    sorted_keys = sorted(payload.keys())
    token_str = ''.join(str(payload[k]) for k in sorted_keys)

    token = hashlib.sha256(token_str.encode()).hexdigest()

    request_payload = {k: v for k, v in payload.items() if k != "Password"}
    request_payload["Token"] = token

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                settings.tinkoff_init_url,
                json=request_payload
            ) as resp:

                data = await resp.json()

                if resp.status != 200:
                    logger.error(f"Tinkoff error: {data}")
                    raise HTTPException(status_code=500, detail=data)

                await create_payment(
                    int(data['PaymentId']),
                    user_id,
                    body.tariff,
                    amount
                )

                return {
                    "data": {
                        "PaymentId": int(data['PaymentId']),
                        "PaymentURL": data['PaymentURL'],
                        "Success": data['Success']
                    }
                }

    except aiohttp.ClientError as e:
        logger.error("Не удалось установить соединение с банком")
        raise HTTPException(status_code=500, detail=str(e))

class RequestCheck(BaseModel):
    payment_id: int

@router.post("/check")
async def check_payment(body: RequestCheck, user_id: int = Depends(get_current_user_id)):

    payload = {
        "TerminalKey": os.getenv("TINKOFF_TERMINAL"),
        "PaymentId": body.payment_id,
        "Password": os.getenv("TINKOFF_PASSWORD"),
    }

    sorted_keys = sorted(payload.keys())
    token_str = ''.join(str(payload[k]) for k in sorted_keys)

    token = hashlib.sha256(token_str.encode()).hexdigest()

    request_payload = {
        "TerminalKey": payload["TerminalKey"],
        "PaymentId": payload["PaymentId"],
        "Token": token,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(
                settings.tinkoff_get_state_url,
                json=request_payload
            ) as resp:

                data = await resp.json()

                if resp.status != 200:
                    logger.error(f"Tinkoff error: {data}")
                    raise HTTPException(status_code=500, detail=data)

                if data.get("Status") == 'CONFIRMED':
                    payment = await get_payment(body.payment_id)
                    if payment['status'] == 'CONFIRMED':
                        return {"status": "ok", "message": "Already processed"}

                    if not payment:
                        raise HTTPException(404, "Payment not found")
                    tariff = payment["tariff"]
                    requests = TARIFFS[tariff]["requests"]
                    await set_user_applications_balance(
                        user_id,
                        requests
                    )
                    await mark_payment_confirmed(body.payment_id)
                return {
                    "status": "success",
                    "payment_status": data.get("Status"),
					"PaymentId": data.get('PaymentId')
                }

    except aiohttp.ClientError as e:
        logger.error("Ошибка соединения с Tinkoff")
        raise HTTPException(status_code=500, detail=str(e))
