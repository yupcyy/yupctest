import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def parse_id_set(value: str) -> frozenset[int]:
    return frozenset(int(part.strip()) for part in value.split(",") if part.strip())


def parse_first_id(value: str) -> int:
    """Accept one ID or a comma-separated list and select the first configured ID."""
    for part in value.split(","):
        part = part.strip()
        if part:
            if not part.isdecimal() or int(part) <= 0:
                raise ValueError("Expected positive numeric ID(s) separated by commas")
            return int(part)
    return 0


@dataclass(frozen=True)
class Settings:
    api_key: str
    model: str
    base_url: str
    ws_url: str
    ws_token: str
    allowed_users: frozenset[int]
    allowed_groups: frozenset[int]
    max_history_turns: int
    max_reply_chars: int
    max_concurrent_requests: int
    chat_max_tokens: int
    qa_max_tokens: int
    technical_max_tokens: int
    detailed_max_tokens: int

    system_prompt: str
    database_path: Path
    enable_usage_tracking: bool
    enable_agent: bool
    enable_persistent_memory: bool
    enable_long_term_memory: bool
    master_qq_id: int

    plugin_config: str = "plugins.json"
    proactive_groups: frozenset[int] = frozenset()
    proactive_probability: float = 0.03
    proactive_cooldown: int = 1800
    owner_proactive_cooldown: int = 43200
    voice_character: str = ""
    voice_source_group: int = 0
    proactive_timezone_offset: int = 8
    mc_server_host: str = ""
    mc_server_port: int = 0
    mc_status_timeout: float = 5.0
    mc_rcon_host: str = ""
    mc_rcon_port: int = 0
    mc_rcon_password: str = ""
    enable_owner_style_learning: bool = True
    enable_companion: bool = False
    companion_persistence: bool = False
    companion_auto_journal: bool = False
    database_type: str = "sqlite"
    database_url: str = ""
    database_username: str = ""
    database_password: str = ""
    enable_remote_backup: bool = False
    remote_backup_interval: int = 300
    building_storage_path: Path = Path("data/building/tasks")
    building_token_ttl: int = 86400
    building_admin_password: str = ""
    gomoku_storage_path: Path = Path("data/gomoku/games")

    @classmethod
    def load(cls) -> "Settings":
        load_dotenv()
        api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
        if not api_key or api_key == "replace_with_your_key":
            raise ValueError("Please set DEEPSEEK_API_KEY in .env")
        project_root = Path(__file__).resolve().parents[3]
        raw_db_path = os.getenv("DATABASE_PATH", "data/agent.sqlite3").strip()
        if not raw_db_path:
            raise ValueError("DATABASE_PATH must not be empty")
        database_path = Path(raw_db_path).expanduser()
        if not database_path.is_absolute():
            database_path = project_root / database_path
        database_type = os.getenv("DATABASE_TYPE", "sqlite").strip().lower()
        if database_type not in {"sqlite", "mysql"}:
            raise ValueError("DATABASE_TYPE must be sqlite or mysql")

        def bool_setting(name: str, default: bool = False) -> bool:
            value = os.getenv(name, str(default)).strip().lower()
            if value in {"true", "1", "yes", "on"}:
                return True
            if value in {"false", "0", "no", "off"}:
                return False
            raise ValueError(f"Invalid boolean setting {name}: {value!r}")

        raw_master = os.getenv("MASTER_QQ_ID", "").strip()
        if raw_master and (not raw_master.isdecimal() or int(raw_master) <= 0):
            raise ValueError("MASTER_QQ_ID must be a positive QQ numeric ID")

        return cls(
            building_storage_path=(project_root / os.getenv("BUILDING_STORAGE_PATH", "data/building/tasks")).resolve(),
            building_token_ttl=max(300, int(os.getenv("BUILDING_TOKEN_TTL", "86400"))),
            building_admin_password=os.getenv("BUILDING_ADMIN_PASSWORD", ""),
            gomoku_storage_path=(project_root / os.getenv("GOMOKU_STORAGE_PATH", "data/gomoku/games")).resolve(),
            plugin_config=os.getenv("PLUGIN_CONFIG", "plugins.json"),
            proactive_groups=parse_id_set(os.getenv("PROACTIVE_GROUPS", "")),
            proactive_probability=min(1.0, max(0.0, float(os.getenv("PROACTIVE_PROBABILITY", "0.03")))),
            proactive_cooldown=max(60, int(os.getenv("PROACTIVE_COOLDOWN", "1800"))),
            owner_proactive_cooldown=max(3600, int(os.getenv("OWNER_PROACTIVE_COOLDOWN", "43200"))),
            voice_character=os.getenv("NAPCAT_VOICE_CHARACTER", "").strip(),
            voice_source_group=parse_first_id(os.getenv("NAPCAT_VOICE_SOURCE_GROUP", "")),
            proactive_timezone_offset=max(-12, min(14, int(os.getenv("PROACTIVE_TIMEZONE_OFFSET", "8")))),
            mc_server_host=os.getenv("MC_SERVER_HOST", "").strip(),
            mc_server_port=max(0, min(65535, int(os.getenv("MC_SERVER_PORT", "0") or 0))),
            mc_status_timeout=max(1.0, min(15.0, float(os.getenv("MC_STATUS_TIMEOUT", "5")))),
            mc_rcon_host=os.getenv("MC_RCON_HOST", "").strip(),
            mc_rcon_port=max(0, min(65535, int(os.getenv("MC_RCON_PORT", "0") or 0))),
            mc_rcon_password=os.getenv("MC_RCON_PASSWORD", ""),
            enable_owner_style_learning=bool_setting("ENABLE_OWNER_STYLE_LEARNING", True),
            enable_companion=bool_setting("ENABLE_COMPANION", False),
            companion_persistence=bool_setting("COMPANION_PERSISTENCE", False),
            companion_auto_journal=bool_setting("COMPANION_AUTO_JOURNAL", False),
            database_type=database_type,
            database_url=os.getenv("DATABASE_URL", "").strip(),
            database_username=os.getenv("DATABASE_USERNAME", "").strip(),
            database_password=os.getenv("DATABASE_PASSWORD", ""),
            enable_remote_backup=bool_setting("ENABLE_REMOTE_BACKUP", False),
            remote_backup_interval=max(60, int(os.getenv("REMOTE_BACKUP_INTERVAL", "300"))),
            api_key=api_key,
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com"),
            ws_url=os.getenv("NAPCAT_WS_URL", "ws://127.0.0.1:3001"),
            ws_token=os.getenv("NAPCAT_TOKEN", ""),
            allowed_users=parse_id_set(os.getenv("ALLOWED_USERS", "")),
            allowed_groups=parse_id_set(os.getenv("ALLOWED_GROUPS", "")),
            max_history_turns=max(1, int(os.getenv("MAX_HISTORY_TURNS", "10"))),
            max_reply_chars=max(100, int(os.getenv("MAX_REPLY_CHARS", "1500"))),
            max_concurrent_requests=max(1, int(os.getenv("MAX_CONCURRENT_REQUESTS", "3"))),
            system_prompt=os.getenv("SYSTEM_PROMPT", "你是一个友善、简洁的QQ聊天助手。"),
            database_path=database_path.resolve(),
            enable_usage_tracking=bool_setting("ENABLE_USAGE_TRACKING", True),
            enable_agent=bool_setting("ENABLE_AGENT", True),
            enable_persistent_memory=bool_setting("ENABLE_PERSISTENT_MEMORY", True),
            enable_long_term_memory=bool_setting("ENABLE_LONG_TERM_MEMORY", True),
            master_qq_id=int(raw_master) if raw_master else 0,
            chat_max_tokens=max(
                32, int(os.getenv("CHAT_MAX_TOKENS", "120"))
            ),
            qa_max_tokens=max(
                32, int(os.getenv("QA_MAX_TOKENS", "220"))
            ),
            technical_max_tokens=max(
                32, int(os.getenv("TECHNICAL_MAX_TOKENS", "500"))
            ),
            detailed_max_tokens=max(
                32, int(os.getenv("DETAILED_MAX_TOKENS", "1200"))
            ),
        )
