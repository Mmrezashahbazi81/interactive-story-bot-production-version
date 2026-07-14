import logging
import uuid
from json import JSONDecodeError

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.services.updates import process_update, summarize_update

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix=f"/{settings.bale_token}",
    tags=["Webhook"],
)


@router.post("/webhook")
async def bale_webhook(request: Request):
    request_id = uuid.uuid4().hex[:12]

    try:
        payload = await request.json()

    except JSONDecodeError:
        raw_body = await request.body()

        logger.warning(
            "Invalid JSON received | request_id=%s | body=%s",
            request_id,
            raw_body.decode("utf-8", errors="replace"),
        )

        return JSONResponse(
            status_code=400,
            content={
                "ok": False,
                "request_id": request_id,
                "error": "Invalid JSON body",
            },
        )

    summary = (
        summarize_update(payload)
        if isinstance(payload, dict)
        else {"kind": "invalid"}
    )

    logger.info(
        "Webhook received | request_id=%s | summary=%s",
        request_id,
        summary,
    )

    if settings.debug and settings.log_update_payload:
        logger.debug("Payload: %s", payload)

    try:
        await process_update(payload)

        logger.info(
            "Webhook processed successfully | request_id=%s",
            request_id,
        )

        return {
            "ok": True,
            "request_id": request_id,
        }

    except Exception:
        logger.exception(
            "Webhook processing failed | request_id=%s | summary=%s",
            request_id,
            summary,
        )

        return JSONResponse(
            status_code=500,
            content={
                "ok": False,
                "request_id": request_id,
                "error": "Internal Server Error",
            },
        )