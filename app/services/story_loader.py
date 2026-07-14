import json
from pathlib import Path
from typing import Any

from app.config import settings
from app.logging_config import get_logger

logger = get_logger(__name__)

# cache
_STORIES: dict[str, dict[str, Any]] = {}
_LOADED = False


def load_story_files(force_reload: bool = False) -> dict[str, dict[str, Any]]:
    global _LOADED

    if _LOADED and not force_reload:
        return _STORIES

    _STORIES.clear()

    stories_path = Path(settings.stories_path)

    if not stories_path.exists():
        logger.warning(
            "stories directory not found",
            extra={"path": str(stories_path)},
        )
        _LOADED = True
        return _STORIES

    loaded = 0

    for file in sorted(stories_path.glob("*.json")):
        try:
            with file.open("r", encoding="utf-8") as f:
                story = json.load(f)

            story_id = story.get("id")

            if not story_id:
                logger.warning(
                    "story without id skipped",
                    extra={"file": file.name},
                )
                continue

            _STORIES[story_id] = story
            loaded += 1

        except Exception:
            logger.exception(
                "failed loading story",
                extra={"file": file.name},
            )

    _LOADED = True

    logger.info(
        "stories loaded",
        extra={
            "count": loaded,
            "directory": str(stories_path),
        },
    )

    return _STORIES


def reload_story_files() -> None:
    load_story_files(force_reload=True)


def get_story_by_id(story_id: str) -> dict[str, Any] | None:
    stories = load_story_files()
    return stories.get(story_id)


def get_all_stories() -> list[dict[str, Any]]:
    return list(load_story_files().values())


def _gender_count(players: list[dict]) -> tuple[int, int]:
    male = sum(
        1
        for player in players
        if player.get("gender") == "male"
    )

    female = sum(
        1
        for player in players
        if player.get("gender") == "female"
    )

    return male, female


def is_story_compatible(
    story: dict[str, Any],
    players: list[dict],
) -> bool:

    player_count = len(players)

    min_players = int(story.get("min_players", 1))
    max_players = int(story.get("max_players", 4))

    if player_count < min_players:
        return False

    if player_count > max_players:
        return False

    roles = story.get("roles", [])

    if not roles:
        return False

    if len(roles) != player_count:
        return False

    male_players, female_players = _gender_count(players)

    male_roles = sum(
        1
        for role in roles
        if role.get("gender", "any") == "male"
    )

    female_roles = sum(
        1
        for role in roles
        if role.get("gender", "any") == "female"
    )

    any_roles = sum(
        1
        for role in roles
        if role.get("gender", "any") == "any"
    )

    if male_players > male_roles + any_roles:
        return False

    if female_players > female_roles + any_roles:
        return False

    return True


def get_compatible_stories(
    players: list[dict],
) -> list[dict[str, Any]]:

    stories = get_all_stories()

    return [
        story
        for story in stories
        if is_story_compatible(story, players)
    ]