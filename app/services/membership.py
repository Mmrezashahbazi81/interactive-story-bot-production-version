from typing import Any
import asyncio
from datetime import datetime, timedelta

from app.bot_api import bale_api
from app.config import settings
from app.db import get_db
from app.logging_config import get_logger

logger = get_logger(__name__)

VALID_MEMBER_STATUSES = {
    "member",
    "administrator",
    "creator",
}


async def get_cached_membership(
    db,
    user_id: int,
    channel_id: str,
    max_age_seconds: int = 300,
) -> str | None:

    cur = await db.execute(
        """
        SELECT
            status,
            checked_at
        FROM memberships
        WHERE
            user_id = ?
            AND channel_id = ?
        """,
        (
            user_id,
            channel_id,
        ),
    )

    row = await cur.fetchone()

    if row is None:
        return None

    try:
        checked_at = datetime.fromisoformat(row["checked_at"])
    except Exception:
        return None

    if datetime.now() - checked_at > timedelta(seconds=max_age_seconds):
        return None

    return row["status"]


async def set_cached_membership(
    db,
    user_id: int,
    channel_id: str,
    status: str,
) -> None:

    await db.execute(
        """
        INSERT INTO memberships
        (
            user_id,
            channel_id,
            status,
            checked_at
        )
        VALUES
        (
            ?,
            ?,
            ?,
            CURRENT_TIMESTAMP
        )

        ON CONFLICT(user_id, channel_id)

        DO UPDATE SET
            status = excluded.status,
            checked_at = CURRENT_TIMESTAMP
        """,
        (
            user_id,
            channel_id,
            status,
        ),
    )


async def _check_single_channel(
    channel_id: str,
    user_id: int,
) -> dict[str, Any]:

    status = "unknown"

    try:

        response = await bale_api.get_chat_member(
            channel_id,
            user_id,
        )

        result = response.get("result", {})
        status = result.get("status", "unknown")

    except Exception:

        logger.exception(
            "Failed checking membership",
            extra={
                "user_id": user_id,
                "channel_id": channel_id,
            },
        )

    return {
        "channel_id": channel_id,
        "status": status,
        "is_member": status in VALID_MEMBER_STATUSES,
    }


async def check_user_membership(
    user_id: int,
) -> tuple[bool, list[dict[str, Any]]]:

    channels = settings.required_channels_list

    if not channels:
        return True, []

    db = await get_db()

    try:

        results: list[dict[str, Any]] = []
        tasks = []
        task_channels = []

        # ---------- Cache ----------
        for channel_id in channels:

            cached = await get_cached_membership(
                db,
                user_id,
                channel_id,
            )

            if cached is not None:

                logger.debug(
                    "Membership cache hit",
                    extra={
                        "user_id": user_id,
                        "channel_id": channel_id,
                    },
                )

                results.append(
                    {
                        "channel_id": channel_id,
                        "status": cached,
                        "is_member": cached in VALID_MEMBER_STATUSES,
                    }
                )

            else:

                logger.debug(
                    "Membership cache miss",
                    extra={
                        "user_id": user_id,
                        "channel_id": channel_id,
                    },
                )

                task_channels.append(channel_id)
                tasks.append(
                    _check_single_channel(
                        channel_id,
                        user_id,
                    )
                )

        # ---------- Parallel API ----------
        if tasks:

            api_results = await asyncio.gather(*tasks)

            for item in api_results:

                await set_cached_membership(
                    db,
                    user_id,
                    item["channel_id"],
                    item["status"],
                )

                results.append(item)

            await db.commit()

        all_ok = all(
            item["is_member"]
            for item in results
        )

        logger.info(
            "Membership check finished",
            extra={
                "user_id": user_id,
                "success": all_ok,
                "checked_channels": len(results),
            },
        )

        return all_ok, results

    finally:
        await db.close()