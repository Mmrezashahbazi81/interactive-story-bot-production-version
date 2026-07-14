from typing import Any

import httpx

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)


class BaleBotAPI:
    def __init__(self) -> None:
        self.base_url = settings.bale_api_base

        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(
                connect=10.0,
                read=20.0,
                write=20.0,
                pool=20.0,
            )
        )

    async def startup(self) -> None:
        return None

    async def close(self) -> None:
        await self.client.aclose()

    async def _post(
        self,
        method: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:

        url = f"{self.base_url}/{method}"

        logger.debug(
            "Bale request",
            extra={
                "method": method,
                "url": url,
            },
        )

        try:
            response = await self.client.post(
                url,
                json=payload,
            )

        except httpx.TimeoutException:
            logger.exception(
                "Bale timeout",
                extra={
                    "method": method,
                },
            )
            raise RuntimeError("Bale API timeout")

        except httpx.HTTPError:
            logger.exception(
                "Bale network error",
                extra={
                    "method": method,
                },
            )
            raise RuntimeError("Bale API network error")

        body = response.text

        if response.status_code >= 400:

            logger.error(
                "Bale HTTP error",
                extra={
                    "method": method,
                    "status": response.status_code,
                    "body": body,
                },
            )

            raise RuntimeError(
                f"Bale HTTP {response.status_code}"
            )

        try:
            data = response.json()

        except ValueError:

            logger.error(
                "Invalid JSON from Bale",
                extra={
                    "method": method,
                    "body": body,
                },
            )

            raise RuntimeError("Invalid Bale response")

        if isinstance(data, dict) and data.get("ok") is False:

            logger.error(
                "Bale logical error",
                extra={
                    "method": method,
                    "response": data,
                },
            )

            raise RuntimeError(str(data))

        logger.debug(
            "Bale request success",
            extra={
                "method": method,
            },
        )

        return data

    async def set_webhook(
        self,
        url: str,
    ) -> dict[str, Any]:

        return await self._post(
            "setWebhook",
            {
                "url": url,
            },
        )

    async def get_webhook_info(
        self,
    ) -> dict[str, Any]:

        return await self._post(
            "getWebhookInfo",
            {},
        )

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        reply_markup: dict[str, Any] | None = None,
        parse_mode: str | None = None,
    ) -> dict[str, Any]:

        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
        }

        if parse_mode:
            payload["parse_mode"] = parse_mode

        if reply_markup:
            payload["reply_markup"] = reply_markup

        return await self._post(
            "sendMessage",
            payload,
        )

    async def edit_message_text(
        self,
        chat_id: int | str,
        message_id: int,
        text: str,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:

        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
        }

        if reply_markup:
            payload["reply_markup"] = reply_markup

        return await self._post(
            "editMessageText",
            payload,
        )

    async def edit_message_reply_markup(
        self,
        chat_id: int | str,
        message_id: int,
        reply_markup: dict[str, Any] | None = None,
    ) -> dict[str, Any]:

        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
        }

        if reply_markup:
            payload["reply_markup"] = reply_markup

        return await self._post(
            "editMessageReplyMarkup",
            payload,
        )

    async def delete_message(
        self,
        chat_id: int | str,
        message_id: int,
    ) -> dict[str, Any]:

        return await self._post(
            "deleteMessage",
            {
                "chat_id": chat_id,
                "message_id": message_id,
            },
        )

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        show_alert: bool = False,
    ) -> dict[str, Any]:

        payload = {
            "callback_query_id": callback_query_id,
            "show_alert": show_alert,
        }

        if text:
            payload["text"] = text

        return await self._post(
            "answerCallbackQuery",
            payload,
        )

    async def get_chat_member(
        self,
        chat_id: int | str,
        user_id: int,
    ) -> dict[str, Any]:

        return await self._post(
            "getChatMember",
            {
                "chat_id": chat_id,
                "user_id": user_id,
            },
        )


bale_api = BaleBotAPI()