import json
from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent


class Settings(BaseSettings):

    bale_token: str = "dummy-token"

    app_base_url: str = "http://localhost:8000"

    webhook_path: str = "/webhook"

    database_path: str = str(BASE_DIR / "data" / "game.db")

    stories_path: str = str(BASE_DIR / "stories")

    required_channels: str = ""

    required_channels_info_raw: str = "[]"

    bot_owner_id: int = 0

    debug: bool = False

    auto_set_webhook: bool = False

    log_update_payload: bool = False

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("bale_token")
    @classmethod
    def validate_token(cls, value: str):
        value = value.strip()

        if not value:
            raise ValueError("BALE_TOKEN is required.")

        return value

    @field_validator("app_base_url")
    @classmethod
    def validate_base_url(cls, value: str):
        return value.rstrip("/")

    @property
    def webhook_url(self) -> str:
        return f"{self.app_base_url}/{self.bale_token}{self.webhook_path}"

    @property
    def bale_api_base(self) -> str:
        return f"https://tapi.bale.ai/bot{self.bale_token}"

    @property
    def required_channels_list(self) -> list[str]:

        if not self.required_channels.strip():
            return []

        return [
            channel.strip()
            for channel in self.required_channels.split(",")
            if channel.strip()
        ]

    @property
    def required_channels_info(self) -> list[dict[str, Any]]:

        try:

            data = json.loads(self.required_channels_info_raw)

            if isinstance(data, list):
                return [x for x in data if isinstance(x, dict)]

        except Exception:
            pass

        return []


settings = Settings()