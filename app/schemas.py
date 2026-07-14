from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, ConfigDict


# ==========================================================
# Bale API Models
# ==========================================================

class BaleResponse(BaseModel):
    ok: bool
    result: Any | None = Field(default=None)
    description: str | None = Field(default=None)

    model_config = ConfigDict(extra="ignore")


class InlineKeyboardButton(BaseModel):
    text: str
    callback_data: str |None = Field(default=None)

    model_config = ConfigDict(extra="ignore")


class InlineKeyboardMarkup(BaseModel):
    inline_keyboard: list[list[InlineKeyboardButton]] = Field(
        default_factory=list
    )

    model_config = ConfigDict(extra="ignore")


# ==========================================================
# Story Models
# ==========================================================

GenderType = Literal[
    "male",
    "female",
    "any",
]


class Choice(BaseModel):
    label: str
    next: str

    model_config = ConfigDict(extra="ignore")


class StoryNode(BaseModel):
    id: str

    text: str = ""

    choices: list[Choice] = Field(
        default_factory=list
    )

    is_ending: bool = False

    image: str | None = None

    metadata: dict[str, Any] = Field(
        default_factory=dict
    )

    model_config = ConfigDict(extra="ignore")


class StoryRole(BaseModel):

    id: str

    name: str

    gender: GenderType = "any"

    description: str = ""

    avatar: str | None = None

    metadata: dict[str, Any] = Field(
        default_factory=dict
    )

    model_config = ConfigDict(extra="ignore")
    
class SendMessageRequest(BaseModel):
    chat_id: int | str
    text: str

    parse_mode: str | None = None

    reply_markup: InlineKeyboardMarkup | None = None


class EditMessageTextRequest(BaseModel):
    chat_id: int | str
    message_id: int

    text: str

    reply_markup: InlineKeyboardMarkup | None = None


class EditMessageReplyMarkupRequest(BaseModel):
    chat_id: int | str
    message_id: int

    reply_markup: InlineKeyboardMarkup | None = None


class DeleteMessageRequest(BaseModel):
    chat_id: int | str
    message_id: int


class AnswerCallbackQueryRequest(BaseModel):
    callback_query_id: str

    text: str | None = None
    show_alert: bool = False


class GetChatMemberRequest(BaseModel):
    chat_id: int | str
    user_id: int


class SetWebhookRequest(BaseModel):
    url: str


class UpdateUser(BaseModel):
    id: int

    first_name: str | None = None
    last_name: str | None = None
    username: str | None = None


class UpdateChat(BaseModel):
    id: int | str

    type: str | None = None
    title: str | None = None        