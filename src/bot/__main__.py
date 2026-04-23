import asyncio
import logging
from threading import Thread

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import BotCommand
from redis.asyncio import Redis

from src.bot.handlers import router
from src.bot.middlewares.db import DbSessionMiddleware
from src.bot.middlewares.metrics import MetricsMiddleware
from src.bot.middlewares.redis import RedisMiddleware
from src.config import settings
from src.db.engine import session_factory
from src.logging_conf import setup_logging

logger = logging.getLogger(__name__)


def start_metrics_server(port: int = 9090) -> None:
    """Start Prometheus metrics HTTP server in a background thread."""
    from prometheus_client import start_http_server

    start_http_server(port)
    logger.info("Prometheus metrics available at http://0.0.0.0:%d/metrics", port)


def create_bot() -> Bot:
    return Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


def create_dispatcher() -> Dispatcher:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)
    storage = RedisStorage(redis)
    dp = Dispatcher(storage=storage)
    dp.update.middleware(DbSessionMiddleware(session_pool=session_factory))
    dp.update.middleware(RedisMiddleware(redis))
    dp.update.middleware(MetricsMiddleware())
    dp.include_router(router)
    return dp


async def set_bot_commands(bot: Bot) -> None:
    await bot.set_my_commands(
        [
            BotCommand(command="start", description="Запустить / вернуться в меню"),
            BotCommand(command="invite", description="Пригласить друга"),
        ]
    )


async def run_polling() -> None:
    bot = create_bot()
    dp = create_dispatcher()
    await bot.delete_webhook(drop_pending_updates=True)
    await set_bot_commands(bot)
    logger.info("Bot started (polling)")
    await dp.start_polling(bot)


async def run_webhook() -> None:
    from aiohttp import web
    from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application

    bot = create_bot()
    dp = create_dispatcher()

    await bot.set_webhook(
        f"{settings.webhook_url}{settings.webhook_path}",
        drop_pending_updates=True,
    )
    await set_bot_commands(bot)

    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(
        app, path=settings.webhook_path
    )
    setup_application(app, dp, bot=bot)

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, settings.webhook_host, settings.webhook_port)
    await site.start()

    logger.info(
        "Bot started (webhook) at %s:%s", settings.webhook_host, settings.webhook_port
    )
    try:
        await asyncio.Event().wait()
    finally:
        await bot.delete_webhook()
        await runner.cleanup()


def main() -> None:
    setup_logging()

    # Start Prometheus metrics server in background thread
    Thread(target=start_metrics_server, daemon=True).start()

    if settings.webhook_enabled:
        asyncio.run(run_webhook())
    else:
        asyncio.run(run_polling())


if __name__ == "__main__":
    main()
