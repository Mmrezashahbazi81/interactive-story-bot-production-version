from contextlib import asynccontextmanager
import logging

from fastapi import FastAPI

from app.bot_api import bale_api
from app.config import settings
from app.db import init_db
from app.logging_config import setup_logging
from app.routers.health import router as health_router
from app.routers.webhook import router as webhook_router

setup_logging()

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        logger.info("========== Application Startup ==========")
        logger.info("Database Path : %s", settings.database_path)
        logger.info("Stories Path  : %s", settings.stories_path)
        logger.info("Webhook URL   : %s", settings.webhook_url)
        logger.info("Debug         : %s", settings.debug)

        # ساخت HTTP Client
        await bale_api.startup()

        # آماده‌سازی دیتابیس
        await init_db()

        # ثبت خودکار Webhook (در صورت فعال بودن)
        if settings.auto_set_webhook:
            logger.info("Setting Bale webhook...")

            result = await bale_api.set_webhook(settings.webhook_url)
            logger.info("Webhook Set Result: %s", result)

            info = await bale_api.get_webhook_info()
            logger.info("Webhook Info: %s", info)

        else:
            logger.info("AUTO_SET_WEBHOOK=False -> skipped")

        logger.info("Startup completed successfully.")

    except Exception:
        logger.exception("Application startup failed.")
        raise

    yield

    logger.info("========== Application Shutdown ==========")

    await bale_api.close()

    logger.info("Shutdown completed.")


app = FastAPI(
    title="Interactive Story Bot",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(webhook_router)