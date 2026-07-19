import uuid
from typing import Any
from pathlib import Path

from app.config import settings
from app.db import get_db
from app.logging_config import get_logger
from app.services.membership import check_user_membership
from app.services.story_loader import get_compatible_stories
from app.utils.keyboards import btn, ikb

_start_status_cache: dict[int, bool] = {}

logger = get_logger(__name__)

GAME_WAITING = "WAITING_PLAYERS"
GAME_ROLE_SELECTION = "ROLE_SELECTION"
GAME_STARTED = "STARTED"
GAME_FINISHED = "FINISHED"

GENDER_LABELS: dict[str, str] = {
    "male": "پسر",
    "female": "دختر",
}


def display_name(user: dict[str, Any]) -> str:
    """
    Build the best display name for a Bale user.
    """

    first = str(user.get("first_name") or "").strip()
    last = str(user.get("last_name") or "").strip()

    full_name = f"{first} {last}".strip()

    if full_name:
        return full_name

    username = str(user.get("username") or "").strip()

    if username:
        return username

    return str(user.get("id", "unknown"))


async def get_user_start_status(
    user_id: int,
) -> bool:

    cached = _start_status_cache.get(user_id)

    if cached is not None:

        logger.debug(
            "Start status cache hit",
            extra={
                "user_id": user_id,
            },
        )

        return cached

    db = await get_db()

    try:

        cur = await db.execute(
            """
            SELECT has_started_private
            FROM users
            WHERE user_id = ?
            """,
            (user_id,),
        )

        row = await cur.fetchone()

        started = bool(
            row and row["has_started_private"]
        )

        _start_status_cache[user_id] = started

        return started

    finally:
        await db.close()


async def ensure_user_can_play(
    user_id: int,
) -> tuple[bool, str]:

    started = await get_user_start_status(user_id)

    if not started:

        logger.info(
            "User has not started private chat",
            extra={
                "user_id": user_id,
            },
        )

        return (
            False,
            "📩 اول باید در PV ربات /start را بزنی.",
        )

    membership_ok, _ = await check_user_membership(user_id)
    
    logger.warning(
    f"membership_ok={membership_ok}, results={_}"
)

    if not membership_ok:

        logger.info(
            "User is not member of required channels",
            extra={
                "user_id": user_id,
            },
        )

        return (
            False,
            "/start رو بزن\n📢 اول باید عضو کانال‌ها و گروه‌ها شوی.",
        )

    return True, ""


async def create_game(
    chat_id: int | str,
    chat_type: str,
    owner_user_id: int,
    owner_name: str,
) -> str:

    logger.warning(
        "CREATE GAME -> DB FILE = %s",
        Path(settings.database_path).resolve(),
    )

    game_id = uuid.uuid4().hex[:10]

    db = await get_db()

    try:

        await db.execute(
            """
            INSERT INTO games
            (
                game_id,
                chat_id,
                chat_type,
                owner_user_id,
                state
            )
            VALUES
            (
                ?, ?, ?, ?, ?
            )
            """,
            (
                game_id,
                chat_id,
                chat_type,
                owner_user_id,
                GAME_WAITING,
            ),
        )

        await db.execute(
            """
            INSERT INTO game_players
            (
                game_id,
                user_id,
                display_name,
                is_ready
            )
            VALUES
            (
                ?, ?, ?, 0
            )
            """,
            (
                game_id,
                owner_user_id,
                owner_name,
            ),
        )

        await db.commit()

        logger.info(
            "Game created",
            extra={
                "game_id": game_id,
                "chat_id": chat_id,
                "owner": owner_user_id,
            },
        )

        return game_id

    finally:
        await db.close()


async def get_game(
    game_id: str,
) -> dict[str, Any] | None:

    db = await get_db()

    try:

        cur = await db.execute(
            """
            SELECT *
            FROM games
            WHERE game_id = ?
            """,
            (game_id,),
        )

        row = await cur.fetchone()

        if row is None:

            logger.debug(
                "Game not found",
                extra={
                    "game_id": game_id,
                },
            )

            return None

        return dict(row)

    finally:
        await db.close()


async def get_players(
    game_id: str,
) -> list[dict[str, Any]]:

    db = await get_db()

    try:

        cur = await db.execute(
            """
            SELECT
                game_id,
                user_id,
                display_name,
                gender,
                role_id,
                turn_order,
                is_ready,
                joined_at
            FROM game_players
            WHERE game_id = ?
            ORDER BY joined_at ASC
            """,
            (game_id,),
        )

        rows = await cur.fetchall()

        return [dict(r) for r in rows]

    finally:
        await db.close()
        
async def add_player(
    game_id: str,
    user_id: int,
    player_name: str,
) -> tuple[bool, str]:
    players = await get_players(game_id)

    if any(p["user_id"] == user_id for p in players):
        return True, "ℹ️ قبلاً وارد بازی شده‌ای."

    if len(players) >= 4:
        return False, "🚫 ظرفیت بازی کامل است."

    db = await get_db()

    try:
        await db.execute(
            """
            INSERT INTO game_players
            (
                game_id,
                user_id,
                display_name,
                is_ready
            )
            VALUES (?, ?, ?, 0)
            """,
            (
                game_id,
                user_id,
                player_name,
            ),
        )

        await db.commit()

        logger.info(
            "Player joined",
            extra={
                "game_id": game_id,
                "user_id": user_id,
            },
        )

        return True, "✅ به بازی اضافه شدی."

    finally:
        await db.close()


async def set_player_gender(
    game_id: str,
    user_id: int,
    gender: str,
) -> tuple[bool, str]:

    if gender not in {"male", "female"}:
        return False, "⚠️ جنسیت نامعتبر است."

    db = await get_db()

    try:

        cur = await db.execute(
            """
            SELECT 1
            FROM game_players
            WHERE game_id = ?
            AND user_id = ?
            """,
            (
                game_id,
                user_id,
            ),
        )

        row = await cur.fetchone()

        if not row:
            return False, "🚪 اول باید وارد بازی شوی."

        await db.execute(
            """
            UPDATE game_players
            SET
                gender = ?,
                is_ready = 1
            WHERE
                game_id = ?
                AND user_id = ?
            """,
            (
                gender,
                game_id,
                user_id,
            ),
        )

        await db.execute(
            """
            UPDATE users
            SET
                gender = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE
                user_id = ?
            """,
            (
                gender,
                user_id,
            ),
        )

        await db.commit()

        logger.info(
            "Gender selected",
            extra={
                "game_id": game_id,
                "user_id": user_id,
                "gender": gender,
            },
        )

        return True, "✅ جنسیت ثبت شد."

    finally:
        await db.close()


async def set_game_story(
    game_id: str,
    story_id: str,
) -> None:

    db = await get_db()

    try:

        await db.execute(
            """
            UPDATE games
            SET
                story_id = ?,
                state = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE game_id = ?
            """,
            (
                story_id,
                GAME_ROLE_SELECTION,
                game_id,
            ),
        )

        await db.commit()

        logger.info(
            "Story selected",
            extra={
                "game_id": game_id,
                "story_id": story_id,
            },
        )

    finally:
        await db.close()


async def render_lobby_text(game_id: str) -> str:

    game = await get_game(game_id)
    players = await get_players(game_id)

    if not game:
        return "❌ بازی پیدا نشد."

    lines = [
        "🎮 لابی بازی",
        "",
        f"کد بازی: {game_id}",
        f"وضعیت: {game['state']}",
        "",
        "بازیکنان:",
    ]

    for index, player in enumerate(players, start=1):

        gender_key = player.get("gender")

        if not isinstance(gender_key, str):
            gender_key = ""

        gender = GENDER_LABELS.get(
            gender_key,
            "ثبت نشده",
        )

        lines.append(
            f"{index}. {player['display_name']} ({gender})"
        )

    lines.extend(
        [
            "",
            "👥 همه بازیکن‌ها باید وارد بازی شوند.",
            "👤 سپس جنسیت خود را انتخاب کنند.",
            "📚 بعد از آماده شدن همه، سازنده داستان را انتخاب می‌کند.",
        ]
    )

    return "\n".join(lines)


def lobby_keyboard(
    game_id: str,
    is_group: bool = True,
) -> dict[str, Any]:

    rows: list[list[dict[str, str]]] = []

    if is_group:
        rows.append(
            [
                btn(
                    "🚪 ورود به بازی",
                    f"l:join:{game_id}",
                )
            ]
        )

    rows.append(
        [
            btn(
                "👦 من پسرم",
                f"l:g:{game_id}:male",
            ),
            btn(
                "👧 من دخترم",
                f"l:g:{game_id}:female",
            ),
        ]
    )

    rows.append(
        [
            btn(
                "📚 انتخاب داستان",
                f"l:stories:{game_id}",
            )
        ]
    )

    return ikb(rows)


async def get_story_selection_text(
    game_id: str,
) -> tuple[str, dict[str, Any] | None]:

    players = await get_players(game_id)

    if not players:
        return "👥 هنوز بازیکنی داخل بازی نیست.", None

    if any(not player.get("gender") for player in players):
        return (
            "⚠️ ابتدا همه بازیکن‌ها باید جنسیت خود را ثبت کنند.",
            None,
        )

    stories = get_compatible_stories(players)

    if not stories:
        return (
            "📭 هیچ داستان سازگاری با ترکیب فعلی بازیکن‌ها پیدا نشد.",
            None,
        )

    lines = [
        "📚 داستان‌های قابل انتخاب",
        "",
        "یکی از داستان‌های زیر را انتخاب کنید:",
        "",
    ]

    rows: list[list[dict[str, str]]] = []

    for story in stories:

        title = story.get("title", story["id"])
        genre = story.get("genre", "-")

        lines.append(f"• {title} ({genre})")

        rows.append(
            [
                btn(
                    title,
                    f"l:story:{game_id}:{story['id']}",
                )
            ]
        )

    logger.info(
        "Compatible stories loaded",
        extra={
            "game_id": game_id,
            "stories_count": len(stories),
        },
    )

    return (
        "\n".join(lines),
        ikb(rows),
    )        