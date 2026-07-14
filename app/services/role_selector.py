from __future__ import annotations

from typing import Any

from app.logging_config import get_logger
from app.services.lobby import GAME_STARTED, get_game, get_players
from app.services.story_loader import get_story_by_id
from app.utils.keyboards import btn, ikb
from app.db import get_db

logger = get_logger(__name__)


def _role_matches_gender(
    role_gender: str,
    player_gender: str | None,
) -> bool:
    """
    بررسی سازگاری جنسیت نقش با بازیکن.
    """

    if player_gender is None:
        return False

    if role_gender == "any":
        return True

    return role_gender == player_gender


async def render_role_selection_text(
    game_id: str,
) -> tuple[str, dict[str, Any] | None]:
    """
    متن و کیبورد انتخاب نقش را تولید می‌کند.
    """

    logger.debug(
        "Rendering role selection",
        extra={
            "game_id": game_id,
        },
    )

    game = await get_game(game_id)

    if game is None:
        return (
            "❌ بازی پیدا نشد.",
            None,
        )

    story_id = game.get("story_id")

    if not isinstance(story_id, str) or not story_id:
        return (
            "📖 هنوز داستانی انتخاب نشده.",
            None,
        )

    story = get_story_by_id(story_id)

    if story is None:
        logger.warning(
            "Story not found",
            extra={
                "story_id": story_id,
                "game_id": game_id,
            },
        )

        return (
            "❌ فایل داستان پیدا نشد.",
            None,
        )

    players = await get_players(game_id)

    taken_roles: set[str] = {
        str(player["role_id"])
        for player in players
        if player.get("role_id")
    }

    lines: list[str] = [
        "🎭 انتخاب نقش",
        f"داستان: {story.get('title', story_id)}",
        "",
        "نقش‌های موجود:",
        "",
    ]

    keyboard_rows: list[list[dict[str, str]]] = []

    roles = story.get("roles", [])

    if not isinstance(roles, list):
        logger.error(
            "Story roles are invalid",
            extra={
                "story_id": story_id,
            },
        )

        return (
            "❌ اطلاعات داستان معتبر نیست.",
            None,
        )

    for role in roles:

        if not isinstance(role, dict):
            continue

        role_id = str(role.get("id", ""))

        if not role_id:
            continue

        role_name = str(
            role.get("name", role_id)
        )

        role_gender = str(
            role.get("gender", "any")
        )

        role_description = str(
            role.get("description", "")
        )

        is_taken = role_id in taken_roles

        status = (
            "❌ گرفته شده"
            if is_taken
            else "✅ آزاد"
        )

        lines.append(
            f"• {role_name}"
        )

        lines.append(
            f"   جنسیت: {role_gender}"
        )

        lines.append(
            f"   وضعیت: {status}"
        )

        if role_description:
            lines.append(
                f"   {role_description}"
            )

        lines.append("")

        if not is_taken:
            keyboard_rows.append(
                [
                    btn(
                        f"🎭 {role_name}",
                        f"r:pick:{game_id}:{role_id}",
                    )
                ]
            )

    lines.extend(
        [
            "────────────",
            "ℹ️ هر بازیکن فقط یک نقش می‌تواند انتخاب کند.",
            "ℹ️ نقش باید با جنسیت انتخاب‌شده سازگار باشد.",
        ]
    )

    reply_markup = (
        ikb(keyboard_rows)
        if keyboard_rows
        else None
    )

    logger.debug(
        "Role selection rendered",
        extra={
            "game_id": game_id,
            "roles": len(roles),
            "available_roles": len(keyboard_rows),
        },
    )

    return (
        "\n".join(lines),
        reply_markup,
    )

async def pick_role(
    game_id: str,
    user_id: int,
    role_id: str,
) -> tuple[bool, str]:
    """
    انتخاب نقش توسط بازیکن.
    """

    logger.info(
        "Player requested role selection",
        extra={
            "game_id": game_id,
            "user_id": user_id,
            "role_id": role_id,
        },
    )

    game = await get_game(game_id)

    if game is None:
        return False, "❌ بازی پیدا نشد."

    story_id = game.get("story_id")

    if not isinstance(story_id, str) or not story_id:
        return False, "📖 هنوز داستانی انتخاب نشده."

    story = get_story_by_id(story_id)

    if story is None:
        logger.warning(
            "Story not found while selecting role",
            extra={
                "story_id": story_id,
                "game_id": game_id,
            },
        )

        return False, "❌ فایل داستان پیدا نشد."

    roles = story.get("roles", [])

    if not isinstance(roles, list):
        return False, "❌ اطلاعات داستان نامعتبر است."

    selected_role: dict[str, Any] | None = None

    for role in roles:
        if not isinstance(role, dict):
            continue

        if str(role.get("id")) == role_id:
            selected_role = role
            break

    if selected_role is None:
        return False, "⚠️ نقش نامعتبر است."

    db = await get_db()

    try:
        await db.execute("BEGIN IMMEDIATE")

        players = await get_players(game_id)

        player = next(
            (
                p
                for p in players
                if p["user_id"] == user_id
            ),
            None,
        )

        if player is None:
            await db.rollback()
            return False, "🚪 ابتدا وارد بازی شوید."

        player_gender = player.get("gender")

        if not isinstance(player_gender, str):
            await db.rollback()
            return False, "⚠️ ابتدا جنسیت خود را انتخاب کنید."

        role_gender = str(
            selected_role.get("gender", "any")
        )

        if not _role_matches_gender(
            role_gender,
            player_gender,
        ):
            await db.rollback()
            return (
                False,
                "🚫 این نقش با جنسیت انتخابی شما سازگار نیست.",
            )

        for other in players:

            if other["user_id"] == user_id:
                continue

            if other.get("role_id") == role_id:
                await db.rollback()
                return (
                    False,
                    "⛔ این نقش قبلاً انتخاب شده است.",
                )

        await db.execute(
            """
            UPDATE game_players
            SET role_id = ?
            WHERE game_id = ?
            AND user_id = ?
            """,
            (
                role_id,
                game_id,
                user_id,
            ),
        )

        await db.commit()

    except Exception:

        await db.rollback()

        logger.exception(
            "Role selection failed",
            extra={
                "game_id": game_id,
                "user_id": user_id,
                "role_id": role_id,
            },
        )

        raise

    finally:
        await db.close()

    logger.info(
        "Role selected successfully",
        extra={
            "game_id": game_id,
            "user_id": user_id,
            "role_id": role_id,
        },
    )

    players = await get_players(game_id)

    if any(
        player.get("role_id") is None
        for player in players
    ):
        return (
            True,
            "✅ نقش با موفقیت ثبت شد.",
        )
        
    role_order: dict[str, int] = {
        str(role["id"]): index
        for index, role in enumerate(roles)
        if isinstance(role, dict) and role.get("id")
    }

    sorted_players = sorted(
        players,
        key=lambda player: role_order.get(
            str(player.get("role_id")),
            9999,
        ),
    )

    first_user_id = (
        sorted_players[0]["user_id"]
        if sorted_players
        else None
    )

    start_node = story.get("start_node")

    if not isinstance(start_node, str) or not start_node:
        logger.error(
            "Story start_node is invalid",
            extra={
                "story_id": story_id,
            },
        )

        return (
            False,
            "❌ نقطه شروع داستان نامعتبر است.",
        )

    db = await get_db()

    try:
        await db.execute("BEGIN IMMEDIATE")

        for player in sorted_players:

            await db.execute(
                """
                UPDATE game_players
                SET turn_order = ?
                WHERE game_id = ?
                AND user_id = ?
                """,
                (
                    role_order.get(
                        str(player["role_id"]),
                        9999,
                    ),
                    game_id,
                    player["user_id"],
                ),
            )

        await db.execute(
            """
            UPDATE games
            SET
                state = ?,
                current_node_id = ?,
                current_turn_user_id = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE game_id = ?
            """,
            (
                GAME_STARTED,
                start_node,
                first_user_id,
                game_id,
            ),
        )

        await db.commit()

    except Exception:

        await db.rollback()

        logger.exception(
            "Failed to start game",
            extra={
                "game_id": game_id,
            },
        )

        raise

    finally:
        await db.close()

    logger.info(
        "Game started successfully",
        extra={
            "game_id": game_id,
            "story_id": story_id,
            "first_turn_user": first_user_id,
            "players": len(sorted_players),
        },
    )

    return (
        True,
        "GAME_STARTED",
    )            