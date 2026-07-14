from __future__ import annotations

from typing import Any
from pathlib import Path

from app.bot_api import bale_api
from app.config import settings
from app.db import get_db
from app.logging_config import get_logger
from app.services.game_engine import apply_choice, render_current_node
from app.services.lobby import (
    add_player,
    create_game,
    display_name,
    ensure_user_can_play,
    get_game,
    get_story_selection_text,
    lobby_keyboard,
    render_lobby_text,
    set_game_story,
    set_player_gender,
)
from app.services.membership import check_user_membership
from app.services.role_selector import (
    pick_role,
    render_role_selection_text,
)
from app.utils.callback_data import unpack_callback

_start_status_cache: dict[int, bool] = {}

logger = get_logger(__name__)


# ==========================================================
# Extract Helpers
# ==========================================================

def extract_chat_id(message: dict[str, Any] | None) -> int | str | None:
    if not isinstance(message, dict):
        return None

    chat = message.get("chat")
    if not isinstance(chat, dict):
        return None

    chat_id = chat.get("id")

    if isinstance(chat_id, (int, str)):
        return chat_id

    return None


def extract_chat_type(message: dict[str, Any] | None) -> str | None:
    if not isinstance(message, dict):
        return None

    chat = message.get("chat")
    if not isinstance(chat, dict):
        return None

    chat_type = chat.get("type")

    return chat_type if isinstance(chat_type, str) else None


def extract_message_id(message: dict[str, Any] | None) -> int | None:
    if not isinstance(message, dict):
        return None

    value = message.get("message_id")

    return value if isinstance(value, int) else None


def extract_user_id(user: dict[str, Any] | None) -> int | None:
    if not isinstance(user, dict):
        return None

    value = user.get("id")

    return value if isinstance(value, int) else None


# ==========================================================
# Summary Helpers
# ==========================================================

def summarize_message(message: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(message, dict):
        return {}

    chat = message.get("chat")
    from_user = message.get("from")

    if not isinstance(chat, dict):
        chat = {}

    if not isinstance(from_user, dict):
        from_user = {}

    return {
        "message_id": message.get("message_id"),
        "chat_id": chat.get("id"),
        "chat_type": chat.get("type"),
        "user_id": from_user.get("id"),
        "text": message.get("text"),
    }


def summarize_update(update: dict[str, Any]) -> dict[str, Any]:
    if "message" in update and isinstance(update["message"], dict):
        return {
            "kind": "message",
            **summarize_message(update["message"]),
        }

    if "callback_query" in update and isinstance(update["callback_query"], dict):

        callback = update["callback_query"]

        message = callback.get("message")
        if not isinstance(message, dict):
            message = {}

        chat = message.get("chat")
        if not isinstance(chat, dict):
            chat = {}

        from_user = callback.get("from")
        if not isinstance(from_user, dict):
            from_user = {}

        return {
            "kind": "callback_query",
            "callback_id": callback.get("id"),
            "data": callback.get("data"),
            "chat_id": chat.get("id"),
            "chat_type": chat.get("type"),
            "message_id": message.get("message_id"),
            "user_id": from_user.get("id"),
        }

    return {
        "kind": "unknown",
        "keys": list(update.keys()),
    }


# ==========================================================
# Membership Keyboard
# ==========================================================

def membership_keyboard() -> dict[str, Any]:
    rows: list[list[dict[str, str]]] = []

    for channel in settings.required_channels_info:

        title = channel.get("title")
        url = channel.get("url")

        if not isinstance(title, str):
            continue

        if not isinstance(url, str):
            continue

        title = title.strip()
        url = url.strip()

        if not title or not url:
            continue

        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"

        rows.append(
            [
                {
                    "text": f"📢 {title}",
                    "url": url,
                }
            ]
        )

    return {
        "inline_keyboard": rows,
    }
    
# ==========================================================
# Safe Bale API Wrappers
# ==========================================================

async def safe_send_message(
    chat_id: int | str | None,
    text: str,
    reply_markup: dict[str, Any] | None = None,
) -> None:
    if chat_id is None:
        logger.warning("Skip send_message: chat_id is None")
        return

    logger.debug(
        "Sending message",
        extra={
            "chat_id": chat_id,
            "text": text[:100],
        },
    )

    try:
        await bale_api.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
        )

    except Exception:
        logger.exception(
            "Failed to send message",
            extra={
                "chat_id": chat_id,
            },
        )
        raise


async def safe_edit_message(
    message: dict[str, Any] | None,
    text: str,
    reply_markup: dict[str, Any] | None = None,
) -> None:

    if not isinstance(message, dict):
        logger.warning("Skip edit_message: invalid message")
        return

    chat_id = extract_chat_id(message)
    message_id = extract_message_id(message)

    if chat_id is None or message_id is None:
        logger.warning(
            "Skip edit_message: missing chat_id/message_id",
            extra={
                "chat_id": chat_id,
                "message_id": message_id,
            },
        )
        return

    logger.debug(
        "Editing message",
        extra={
            "chat_id": chat_id,
            "message_id": message_id,
        },
    )

    try:

        await bale_api.edit_message_text(
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            reply_markup=reply_markup,
        )

    except Exception:

        logger.exception(
            "Edit failed, fallback to send_message",
            extra={
                "chat_id": chat_id,
                "message_id": message_id,
            },
        )

        await safe_send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
        )


async def safe_answer_callback_query(
    callback_id: str | None,
    text: str | None = None,
    show_alert: bool = False,
) -> None:

    if not callback_id:
        logger.warning("Skip answer_callback_query: callback_id empty")
        return

    logger.debug(
        "Answer callback",
        extra={
            "callback_id": callback_id,
        },
    )

    try:

        await bale_api.answer_callback_query(
            callback_query_id=callback_id,
            text=text,
            show_alert=show_alert,
        )

    except Exception:

        logger.exception(
            "Failed to answer callback",
            extra={
                "callback_id": callback_id,
            },
        )

        raise


# ==========================================================
# User Persistence
# ==========================================================

async def save_user_from_message(
    message: dict[str, Any],
) -> None:

    from_user = message.get("from")

    if not isinstance(from_user, dict):
        return

    user_id = extract_user_id(from_user)

    if user_id is None:
        return

    first_name = (
        from_user.get("first_name")
        if isinstance(from_user.get("first_name"), str)
        else None
    )

    last_name = (
        from_user.get("last_name")
        if isinstance(from_user.get("last_name"), str)
        else None
    )

    username = (
        from_user.get("username")
        if isinstance(from_user.get("username"), str)
        else None
    )

    logger.warning(
        "SAVE USER -> DB FILE = %s",
        Path(settings.database_path).resolve(),
    )

    db = await get_db()

    try:

        await db.execute(
            """
            INSERT INTO users
            (
                user_id,
                first_name,
                last_name,
                username,
                has_started_private
            )
            VALUES (?, ?, ?, ?, 1)

            ON CONFLICT(user_id)
            DO UPDATE SET
                first_name = excluded.first_name,
                last_name = excluded.last_name,
                username = excluded.username,
                has_started_private = 1,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                user_id,
                first_name,
                last_name,
                username,
            ),
        )

        await db.commit()
        
        _start_status_cache[user_id] = True

        cur = await db.execute(
            """
            SELECT
                user_id,
                has_started_private
            FROM users
            WHERE user_id = ?
            """,
            (user_id,),
        )

        row = await cur.fetchone()

        logger.warning(
            "ROW AFTER SAVE = %s",
            dict(row) if row else None,
        )

        logger.debug(
            "User saved",
            extra={
                "user_id": user_id,
            },
        )

    finally:
        await db.close()


# ==========================================================
# Membership Check
# ==========================================================

async def ensure_user_membership_or_message(
    chat_id: int | str | None,
    user_id: int,
) -> bool:

    membership_ok, results = await check_user_membership(user_id)

    if membership_ok:
        return True

    lines = [
        "📢 برای استفاده از ربات ابتدا عضو کانال‌های زیر شوید:",
        "",
    ]

    for item in results:

        if item["is_member"]:
            continue

        title = next(
            (
                channel.get("title")
                for channel in settings.required_channels_info
                if channel.get("id") == item["channel_id"]
            ),
            item["channel_id"],
        )

        lines.append(f"• {title}")

    lines.extend(
        [
            "",
            "بعد از عضویت دوباره /start را ارسال کنید.",
        ]
    )

    await safe_send_message(
        chat_id,
        "\n".join(lines),
        reply_markup=membership_keyboard(),
    )

    logger.info(
        "User is not member of required channels",
        extra={
            "user_id": user_id,
        },
    )

    return False

# ==========================================================
# Command Handlers
# ==========================================================

async def handle_start_command(
    message: dict[str, Any],
) -> None:

    chat = message.get("chat", {})
    chat_type = extract_chat_type(message)
    chat_id = extract_chat_id(message)

    user = message.get("from", {})
    user_id = extract_user_id(user)

    if chat_id is None or user_id is None:
        logger.warning("Invalid /start message")
        return

    await save_user_from_message(message)

    logger.info(
        "Handling /start",
        extra={
            "user_id": user_id,
            "chat_type": chat_type,
        },
    )

    if chat_type != "private":

        await safe_send_message(
            chat_id,
            (
                "سلام 👋\n\n"
                "برای استفاده از ربات ابتدا در گفتگوی خصوصی ربات دستور /start را اجرا کن."
            ),
        )
        return

    membership_ok = await ensure_user_membership_or_message(
        chat_id=chat_id,
        user_id=user_id,
    )

    if not membership_ok:
        return

    await safe_send_message(
        chat_id,
        (
            "✅ خوش آمدی.\n\n"
            "اکنون می‌توانی ربات را در گروه اضافه کرده و بازی جدید بسازی."
        ),
    )


async def handle_newgame_command(
    message: dict[str, Any],
) -> None:

    chat = message.get("chat", {})
    chat_type = extract_chat_type(message)
    chat_id = extract_chat_id(message)

    user = message.get("from", {})
    owner_id = extract_user_id(user)

    if chat_id is None or owner_id is None:
        logger.warning("Invalid /newgame message")
        return

    if chat_type == "private":

        await safe_send_message(
            chat_id,
            "❌ این دستور فقط داخل گروه قابل استفاده است.",
        )
        return

    allowed, reason = await ensure_user_can_play(owner_id)

    if not allowed:

        await safe_send_message(
            chat_id,
            reason,
        )
        return

    owner_name = display_name(user)

    game_id = await create_game(
        chat_id=chat_id,
        chat_type=chat_type,
        owner_user_id=owner_id,
        owner_name=owner_name,
    )

    text = await render_lobby_text(game_id)

    await safe_send_message(
        chat_id,
        text,
        reply_markup=lobby_keyboard(game_id),
    )

    logger.info(
        "Game created",
        extra={
            "game_id": game_id,
            "owner_id": owner_id,
            "chat_id": chat_id,
        },
    )
    
# ==========================================================
# Callback Dispatcher
# ==========================================================

async def handle_callback_query(
    callback: dict[str, Any],
) -> None:

    callback_id = callback.get("id")

    from_user = callback.get("from")
    if not isinstance(from_user, dict):
        logger.warning("Callback without user")
        return

    user_id = extract_user_id(from_user)
    if user_id is None:
        logger.warning("Callback without user_id")
        return

    data = callback.get("data")
    parts = unpack_callback(data)

    if len(parts) < 2:
        logger.warning(
            "Invalid callback data",
            extra={
                "data": data,
            },
        )
        return

    logger.info(
        "Callback received",
        extra={
            "user_id": user_id,
            "callback": data,
        },
    )

    prefix = parts[0]

    try:

        if prefix == "l":
            await handle_lobby_callback(
                callback=callback,
                parts=parts,
            )
            return

        if prefix == "r":
            await handle_role_callback(
                callback=callback,
                parts=parts,
            )
            return

        if prefix == "s":
            await handle_story_callback(
                callback=callback,
                parts=parts,
            )
            return

        await safe_answer_callback_query(
            callback_id,
            "درخواست نامعتبر است.",
            show_alert=True,
        )

    except Exception:

        logger.exception(
            "Callback handler failed",
            extra={
                "callback": data,
                "user_id": user_id,
            },
        )

        await safe_answer_callback_query(
            callback_id,
            "خطایی رخ داد.",
            show_alert=True,
        )


# ==========================================================
# Lobby Callback Dispatcher
# ==========================================================

async def handle_lobby_callback(
    callback: dict[str, Any],
    parts: list[str],
) -> None:

    action = parts[1]

    if action == "join":
        await callback_join_game(callback, parts)
        return

    if action == "g":
        await callback_select_gender(callback, parts)
        return

    if action == "stories":
        await callback_show_stories(callback, parts)
        return

    if action == "story":
        await callback_select_story(callback, parts)
        return

    await safe_answer_callback_query(
        callback.get("id"),
        "دستور ناشناخته.",
    )


# ==========================================================
# Role Callback Dispatcher
# ==========================================================

async def handle_role_callback(
    callback: dict[str, Any],
    parts: list[str],
) -> None:

    action = parts[1]

    if action == "pick":
        await callback_pick_role(callback, parts)
        return

    await safe_answer_callback_query(
        callback.get("id"),
        "دستور ناشناخته.",
    )


# ==========================================================
# Story Callback Dispatcher
# ==========================================================

async def handle_story_callback(
    callback: dict[str, Any],
    parts: list[str],
) -> None:

    action = parts[1]

    if action == "go":
        await callback_story_choice(callback, parts)
        return

    await safe_answer_callback_query(
        callback.get("id"),
        "دستور ناشناخته.",
    )
    
# ==========================================================
# Lobby Callbacks
# ==========================================================

async def callback_join_game(
    callback: dict[str, Any],
    parts: list[str],
) -> None:

    callback_id = callback.get("id")

    if len(parts) != 3:
        await safe_answer_callback_query(
            callback_id,
            "درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    game_id = parts[2]

    from_user = callback.get("from")
    if not isinstance(from_user, dict):
        return

    user_id = extract_user_id(from_user)
    if user_id is None:
        return

    allowed, reason = await ensure_user_can_play(user_id)

    if not allowed:

        await safe_answer_callback_query(
            callback_id,
            reason,
            show_alert=True,
        )
        return

    ok, message = await add_player(
        game_id=game_id,
        user_id=user_id,
        player_name=display_name(from_user),
    )

    await safe_answer_callback_query(
        callback_id,
        message,
    )

    if not ok:
        return

    game = await get_game(game_id)

    if game is None:
        logger.warning(
            "Game disappeared after join",
            extra={
                "game_id": game_id,
            },
        )
        return

    text = await render_lobby_text(game_id)

    message_obj = callback.get("message")

    await safe_edit_message(
        message=message_obj,
        text=text,
        reply_markup=lobby_keyboard(
            game_id=game_id,
            is_group=game.get("chat_type") != "private",
        ),
    )

    logger.info(
        "Player joined game",
        extra={
            "game_id": game_id,
            "user_id": user_id,
        },
    )
    
async def callback_select_gender(
    callback: dict[str, Any],
    parts: list[str],
) -> None:

    callback_id = callback.get("id")

    if len(parts) != 4:
        await safe_answer_callback_query(
            callback_id,
            "درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    game_id = parts[2]
    gender = parts[3]

    from_user = callback.get("from")
    if not isinstance(from_user, dict):
        return

    user_id = extract_user_id(from_user)
    if user_id is None:
        return

    ok, message = await set_player_gender(
        game_id=game_id,
        user_id=user_id,
        gender=gender,
    )

    await safe_answer_callback_query(
        callback_id,
        message,
        show_alert=not ok,
    )

    if not ok:
        logger.info(
            "Gender selection rejected",
            extra={
                "game_id": game_id,
                "user_id": user_id,
                "gender": gender,
            },
        )
        return

    game = await get_game(game_id)
    if game is None:
        logger.warning(
            "Game not found after gender selection",
            extra={
                "game_id": game_id,
            },
        )
        return

    text = await render_lobby_text(game_id)

    await safe_edit_message(
        message=callback.get("message"),
        text=text,
        reply_markup=lobby_keyboard(
            game_id=game_id,
            is_group=game.get("chat_type") != "private",
        ),
    )

    logger.info(
        "Player selected gender",
        extra={
            "game_id": game_id,
            "user_id": user_id,
            "gender": gender,
        },
    )
    
async def callback_show_stories(
    callback: dict[str, Any],
    parts: list[str],
) -> None:

    callback_id = callback.get("id")

    if len(parts) != 3:
        await safe_answer_callback_query(
            callback_id,
            "درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    game_id = parts[2]

    text, keyboard = await get_story_selection_text(game_id)

    await safe_edit_message(
        message=callback.get("message"),
        text=text,
        reply_markup=keyboard,
    )

    await safe_answer_callback_query(
        callback_id,
    )

    logger.info(
        "Story list displayed",
        extra={
            "game_id": game_id,
        },
    )
    
async def callback_pick_role(
    callback: dict[str, Any],
    parts: list[str],
) -> None:

    callback_id = callback.get("id")

    if len(parts) != 4:
        await safe_answer_callback_query(
            callback_id,
            "درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    game_id = parts[2]
    role_id = parts[3]

    from_user = callback.get("from")
    if not isinstance(from_user, dict):
        return

    user_id = extract_user_id(from_user)
    if user_id is None:
        return

    ok, result = await pick_role(
        game_id=game_id,
        user_id=user_id,
        role_id=role_id,
    )

    await safe_answer_callback_query(
        callback_id,
        result,
        show_alert=not ok,
    )

    if not ok:

        logger.info(
            "Role selection rejected",
            extra={
                "game_id": game_id,
                "user_id": user_id,
                "role_id": role_id,
            },
        )
        return

    # --------------------------------------------------
    # هنوز بازی شروع نشده
    # --------------------------------------------------

    if result != "GAME_STARTED":

        text, keyboard = await render_role_selection_text(
            game_id,
        )

        await safe_edit_message(
            message=callback.get("message"),
            text=text,
            reply_markup=keyboard,
        )

        logger.info(
            "Role selected",
            extra={
                "game_id": game_id,
                "user_id": user_id,
                "role_id": role_id,
            },
        )

        return

    # --------------------------------------------------
    # بازی شروع شده
    # --------------------------------------------------

    text, keyboard = await render_current_node(
        game_id,
    )

    await safe_edit_message(
        message=callback.get("message"),
        text=text,
        reply_markup=keyboard,
    )

    logger.info(
        "Game started",
        extra={
            "game_id": game_id,
        },
    )
    
async def callback_story_choice(
    callback: dict[str, Any],
    parts: list[str],
) -> None:

    callback_id = callback.get("id")

    if len(parts) != 4:
        await safe_answer_callback_query(
            callback_id,
            "درخواست نامعتبر است.",
            show_alert=True,
        )
        return

    game_id = parts[2]
    next_node_id = parts[3]

    from_user = callback.get("from")
    if not isinstance(from_user, dict):
        return

    user_id = extract_user_id(from_user)
    if user_id is None:
        return

    ok, result = await apply_choice(
        game_id=game_id,
        user_id=user_id,
        next_node_id=next_node_id,
    )

    await safe_answer_callback_query(
        callback_id,
        None if ok else result,
        show_alert=not ok,
    )

    if not ok:

        logger.info(
            "Story choice rejected",
            extra={
                "game_id": game_id,
                "user_id": user_id,
                "next_node": next_node_id,
            },
        )
        return

    text, keyboard = await render_current_node(
        game_id,
    )

    await safe_edit_message(
        message=callback.get("message"),
        text=text,
        reply_markup=keyboard,
    )

    if result == "ENDED":

        logger.info(
            "Game finished",
            extra={
                "game_id": game_id,
                "user_id": user_id,
            },
        )

    else:

        logger.info(
            "Story advanced",
            extra={
                "game_id": game_id,
                "user_id": user_id,
                "next_node": next_node_id,
            },
        )
        
# ==========================================================
# Main Update Dispatcher
# ==========================================================

async def process_update(
    payload: dict[str, Any],
) -> None:

    logger.info(
        "Processing update",
        extra={
            "update_keys": list(payload.keys()),
        },
    )

    # --------------------------------------------------
    # Callback Query
    # --------------------------------------------------

    callback = payload.get("callback_query")

    if isinstance(callback, dict):

        await handle_callback_query(callback)
        return

    # --------------------------------------------------
    # Message
    # --------------------------------------------------

    message = payload.get("message")

    if not isinstance(message, dict):

        logger.debug("Ignoring unknown update")
        return

    text = message.get("text")

    if not isinstance(text, str):

        logger.debug("Ignoring non-text message")
        return

    text = text.strip()

    logger.info(
        "Incoming message",
        extra={
            "text": text,
            "chat_id": extract_chat_id(message),
            "user_id": extract_user_id(message.get("from")),
        },
    )

    # --------------------------------------------------
    # Commands
    # --------------------------------------------------

    if text.startswith("/start"):

        await handle_start_command(message)
        return

    if text.startswith("/newgame"):

        await handle_newgame_command(message)
        return

    # --------------------------------------------------
    # Unknown command
    # --------------------------------------------------

    if text.startswith("/"):

        await safe_send_message(
            chat_id=extract_chat_id(message),
            text="❓ دستور ناشناخته است.",
        )
        return

    logger.debug(
        "Ignoring normal message",
        extra={
            "text": text[:100],
        },
    )                                   