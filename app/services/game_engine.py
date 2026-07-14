from __future__ import annotations

import json
from typing import Any

from app.db import get_db
from app.logging_config import get_logger
from app.services.lobby import (
    GAME_FINISHED,
    GAME_STARTED,
    get_game,
    get_players,
)
from app.services.story_loader import get_story_by_id
from app.utils.callback_data import pack_callback
from app.utils.keyboards import btn, ikb


logger = get_logger(__name__)


def _next_turn_user(
    players: list[dict[str, Any]],
    current_user_id: int,
) -> int | None:
    """
    Return next player's user_id according to turn_order.
    """

    ordered_players = sorted(
        players,
        key=lambda player: (
            player.get("turn_order") is None,
            player.get("turn_order", 9999),
        ),
    )

    if not ordered_players:
        return None

    ordered_ids = [
        int(player["user_id"])
        for player in ordered_players
    ]

    if current_user_id not in ordered_ids:
        return ordered_ids[0]

    current_index = ordered_ids.index(current_user_id)

    return ordered_ids[
        (current_index + 1) % len(ordered_ids)
    ]


async def render_current_node(
    game_id: str,
) -> tuple[str, dict[str, Any] | None]:
    """
    Render current story node and its inline keyboard.
    """

    game = await get_game(game_id)

    if (
        game is None
        or not game.get("story_id")
        or not game.get("current_node_id")
    ):
        return (
            "بازی هنوز شروع نشده است.",
            None,
        )

    story = get_story_by_id(
        str(game["story_id"])
    )

    if story is None:
        logger.error(
            "Story not found",
            extra={
                "story_id": game["story_id"],
            },
        )
        return (
            "فایل داستان پیدا نشد.",
            None,
        )

    nodes = story.get("nodes", {})

    node = nodes.get(
        game["current_node_id"]
    )

    if node is None:
        logger.error(
            "Current node not found",
            extra={
                "story_id": story.get("id"),
                "node_id": game["current_node_id"],
            },
        )

        return (
            "گره فعلی داستان پیدا نشد.",
            None,
        )

    players = await get_players(game_id)

    current_player = next(
        (
            player
            for player in players
            if player["user_id"]
            == game.get("current_turn_user_id")
        ),
        None,
    )

    lines: list[str] = [
        f"📖 {story.get('title', story['id'])}",
        "",
        str(node.get("text", "")),
    ]

    if (
        current_player is not None
        and not node.get("is_ending")
    ):
        lines.extend(
            [
                "",
                f"🎯 نوبت: {current_player['display_name']}",
            ]
        )

    choices = node.get("choices", [])

    if node.get("is_ending") or not choices:
        return (
            "\n".join(lines),
            None,
        )

    keyboard_rows: list[list[dict[str, str]]] = []

    for choice in choices:
        keyboard_rows.append(
            [
                btn(
                    str(choice["label"]),
                    pack_callback(
                        "s",
                        "go",
                        game_id,
                        str(choice["next"]),
                    ),
                )
            ]
        )

    return (
        "\n".join(lines),
        ikb(keyboard_rows),
    )
    
async def apply_choice(
    game_id: str,
    user_id: int,
    next_node_id: str,
) -> tuple[bool, str]:
    """
    Apply a player's choice and advance the game.
    """

    game = await get_game(game_id)

    if game is None:
        return False, "بازی پیدا نشد."

    if game["state"] != GAME_STARTED:
        return False, "بازی در حال اجرا نیست."

    if game["current_turn_user_id"] != user_id:
        return False, "الان نوبت شما نیست."

    story = get_story_by_id(str(game["story_id"]))

    if story is None:
        logger.error(
            "Story not found while applying choice",
            extra={
                "story_id": game["story_id"],
                "game_id": game_id,
            },
        )
        return False, "فایل داستان پیدا نشد."

    current_node = story.get("nodes", {}).get(
        game["current_node_id"]
    )

    if current_node is None:
        logger.error(
            "Current node missing",
            extra={
                "game_id": game_id,
                "node_id": game["current_node_id"],
            },
        )
        return False, "گره فعلی داستان نامعتبر است."

    valid_next_nodes = {
        str(choice["next"])
        for choice in current_node.get("choices", [])
    }

    if next_node_id not in valid_next_nodes:
        return False, "انتخاب نامعتبر است."

    next_node = story.get("nodes", {}).get(next_node_id)

    if next_node is None:
        logger.error(
            "Next node missing",
            extra={
                "game_id": game_id,
                "next_node": next_node_id,
            },
        )
        return False, "گره بعدی پیدا نشد."

    players = await get_players(game_id)

    db = await get_db()

    try:
        await db.execute("BEGIN IMMEDIATE")

        if next_node.get("is_ending", False):

            await db.execute(
                """
                UPDATE games
                SET
                    current_node_id=?,
                    state=?,
                    current_turn_user_id=NULL,
                    updated_at=CURRENT_TIMESTAMP
                WHERE game_id=?
                """,
                (
                    next_node_id,
                    GAME_FINISHED,
                    game_id,
                ),
            )

        else:

            next_turn_user = _next_turn_user(
                players,
                user_id,
            )

            await db.execute(
                """
                UPDATE games
                SET
                    current_node_id=?,
                    current_turn_user_id=?,
                    updated_at=CURRENT_TIMESTAMP
                WHERE game_id=?
                """,
                (
                    next_node_id,
                    next_turn_user,
                    game_id,
                ),
            )

        payload = json.dumps(
            {
                "next_node": next_node_id,
            },
            ensure_ascii=False,
        )

        await db.execute(
            """
            INSERT INTO game_events
            (
                game_id,
                user_id,
                event_type,
                payload_json
            )
            VALUES
            (?, ?, ?, ?)
            """,
            (
                game_id,
                user_id,
                "choice",
                payload,
            ),
        )

        await db.commit()

    except Exception:

        await db.rollback()

        logger.exception(
            "Failed to apply story choice",
            extra={
                "game_id": game_id,
                "user_id": user_id,
                "next_node": next_node_id,
            },
        )

        raise

    finally:
        await db.close()

    logger.info(
        "Choice applied",
        extra={
            "game_id": game_id,
            "user_id": user_id,
            "next_node": next_node_id,
        },
    )

    if next_node.get("is_ending", False):

        logger.info(
            "Game finished",
            extra={
                "game_id": game_id,
            },
        )

        return True, "ENDED"

    return True, "OK"    