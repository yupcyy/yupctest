from pathlib import Path

from qq_deepseek.storage.mysql import connection_config


def test_jdbc_mysql_config_is_scoped_to_one_database():
    cfg=connection_config("jdbc:mysql://db.example:3307/agent_data?useSSL=true","agent_user","secret")
    assert cfg["host"] == "db.example"
    assert cfg["port"] == 3307
    assert cfg["database"] == "agent_data"
    assert cfg["user"] == "agent_user"


def test_schema_contains_only_expected_agent_tables():
    sql=(Path(__file__).resolve().parents[1]/"scripts/database/schema_mysql.sql").read_text()
    expected={"agent_conversation_messages","agent_memories","agent_owner_style_samples",
              "agent_user_state","agent_chat_preferences","agent_runtime_state","agent_llm_usage"}
    import re
    found=set(re.findall(r"CREATE TABLE IF NOT EXISTS ([a-z_]+)",sql))
    assert found == expected
