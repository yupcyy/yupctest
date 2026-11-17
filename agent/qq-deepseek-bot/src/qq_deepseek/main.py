import asyncio
import logging
import sys
from contextlib import suppress
from pathlib import Path

from qq_deepseek.adapters.onebot_ws import OneBotWS
from qq_deepseek.core.config import Settings
from qq_deepseek.core.reply_mode import ReplyPolicy
from qq_deepseek.core.router import Router
from qq_deepseek.providers.deepseek import DeepSeekProvider
from qq_deepseek.services.chat import ChatService
from qq_deepseek.services.memory_service import MemoryService
from qq_deepseek.services.usage_service import UsageService
from qq_deepseek.storage.memory import InMemoryHistory
from qq_deepseek.storage.memory_sqlite import SQLiteMemoryStore
from qq_deepseek.storage.usage import SQLiteUsageStore

logger = logging.getLogger(__name__)


async def remote_backup_loop(settings) -> None:
    """Periodically mirror local SQLite rows to MySQL without blocking chat."""
    script = Path(__file__).resolve().parents[2] / "scripts" / "database" / "migrate_sqlite.py"
    while True:
        await asyncio.sleep(settings.remote_backup_interval)
        try:
            process = await asyncio.create_subprocess_exec(
                sys.executable, str(script), "--confirm", "MIGRATE_SQLITE_TO_MYSQL",
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT,
            )
            output, _ = await asyncio.wait_for(process.communicate(), timeout=120)
            message = output.decode("utf-8", "replace").strip()
            if process.returncode == 0:
                logger.info("Remote backup completed: %s", message)
            else:
                logger.warning("Remote backup failed with code %s: %s", process.returncode, message)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Remote backup failed; local chat storage remains available")


def create_chat(settings, provider, history, usage_service, memory_service=None):
    reply_policy = ReplyPolicy(
        chat=settings.chat_max_tokens,
        qa=settings.qa_max_tokens,
        technical=settings.technical_max_tokens,
        detailed=settings.detailed_max_tokens,
    )
    if not settings.enable_agent:
        return ChatService(provider, history, settings.system_prompt, memory_service=memory_service, reply_policy=reply_policy)

    from qq_deepseek.agent.framework import FrameworkAgent
    return FrameworkAgent(settings, provider, history, memory_service, reply_policy)


async def run() -> None:
    settings = Settings.load()
    if settings.enable_remote_backup and settings.database_type != "sqlite":
        raise ValueError("ENABLE_REMOTE_BACKUP requires DATABASE_TYPE=sqlite")
    if settings.database_type == "mysql":
        from qq_deepseek.storage.mysql import MySQLMemoryStore, MySQLUsageStore
        memory_factory = lambda: MySQLMemoryStore(settings.database_url, settings.database_username,
                                                   settings.database_password, settings.max_history_turns)
        usage_factory = lambda: MySQLUsageStore(settings.database_url, settings.database_username,
                                                 settings.database_password)
    else:
        memory_factory = lambda: SQLiteMemoryStore(settings.database_path, settings.max_history_turns)
        usage_factory = lambda: SQLiteUsageStore(settings.database_path)
    store = None
    usage_service = None
    if settings.enable_usage_tracking:
        store = usage_factory()
        usage_service = UsageService(store)
        logger.info("Usage database initialized using %s", settings.database_type)

    provider = None
    memory_store = None
    backup_task = None
    try:
        provider = DeepSeekProvider(
            settings.api_key, settings.base_url, settings.model,
            usage_service=usage_service,
        )
        if settings.enable_persistent_memory or settings.enable_long_term_memory:
            memory_store = memory_factory()
        history = (memory_store if settings.enable_persistent_memory else InMemoryHistory(settings.max_history_turns))
        memory_service = (MemoryService(memory_store, settings.master_qq_id, settings.enable_long_term_memory,
                                        settings.enable_owner_style_learning)
                          if memory_store is not None else None)
        chat = create_chat(settings, provider, history, usage_service, memory_service)
        router = Router(chat, settings.allowed_users, settings.allowed_groups, memory_service,
                        settings=settings)
        adapter = OneBotWS(
            settings.ws_url, settings.ws_token, router,
            settings.max_reply_chars, settings.max_concurrent_requests,
        )
        if settings.enable_remote_backup:
            backup_task = asyncio.create_task(remote_backup_loop(settings), name="remote-mysql-backup")
            logger.info("Remote MySQL backup enabled every %s seconds", settings.remote_backup_interval)
        await adapter.run()
    finally:
        if backup_task is not None:
            backup_task.cancel()
            with suppress(asyncio.CancelledError):
                await backup_task
        if provider is not None:
            await provider.close()
        if memory_store is not None:
            await asyncio.to_thread(memory_store.close)
        if store is not None:
            await asyncio.to_thread(store.close)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
