CREATE TABLE IF NOT EXISTS agent_conversation_messages (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  source_sqlite_id BIGINT UNSIGNED NULL UNIQUE,
  conversation_id VARCHAR(96) NOT NULL,
  role ENUM('user','assistant') NOT NULL,
  content TEXT NOT NULL,
  created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  INDEX idx_agent_conversation (conversation_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS agent_memories (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  source_sqlite_id BIGINT UNSIGNED NULL UNIQUE,
  user_id BIGINT UNSIGNED NOT NULL,
  content VARCHAR(400) NOT NULL,
  created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6),
  INDEX idx_agent_memories_user (user_id,id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS agent_owner_style_samples (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT PRIMARY KEY,
  source_sqlite_id BIGINT UNSIGNED NULL UNIQUE,
  content VARCHAR(80) NOT NULL,
  created_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS agent_user_state (
  user_id BIGINT UNSIGNED NOT NULL PRIMARY KEY,
  affinity SMALLINT NOT NULL DEFAULT 0,
  blocked BOOLEAN NOT NULL DEFAULT FALSE,
  block_reason VARCHAR(120) NOT NULL DEFAULT '',
  rate_window_start DOUBLE NOT NULL DEFAULT 0,
  rate_call_count SMALLINT UNSIGNED NOT NULL DEFAULT 0,
  gift_day DATE NULL,
  gift_count TINYINT UNSIGNED NOT NULL DEFAULT 0,
  sleep_started_at DOUBLE NULL,
  updated_at TIMESTAMP(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6),
  CONSTRAINT chk_agent_affinity CHECK (affinity BETWEEN -100 AND 100)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS agent_chat_preferences (
  scope ENUM('private','group') NOT NULL,
  target_id BIGINT UNSIGNED NOT NULL,
  name VARCHAR(48) NOT NULL,
  value VARCHAR(128) NOT NULL,
  PRIMARY KEY(scope,target_id,name)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS agent_runtime_state (
  state_key VARCHAR(128) NOT NULL,
  last_proactive_at DOUBLE NULL,
  game_board JSON NULL,
  game_updated_at TIMESTAMP(6) NULL,
  PRIMARY KEY(state_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS agent_llm_usage (
  request_id CHAR(36) NOT NULL PRIMARY KEY,
  created_at VARCHAR(40) NOT NULL,
  model VARCHAR(96) NOT NULL,
  conversation_id VARCHAR(96) NOT NULL,
  operation VARCHAR(64) NOT NULL,
  prompt_tokens INT UNSIGNED NOT NULL,
  completion_tokens INT UNSIGNED NOT NULL,
  cache_hit_tokens INT UNSIGNED NULL,
  cache_miss_tokens INT UNSIGNED NULL,
  INDEX idx_agent_usage_created (created_at),
  INDEX idx_agent_usage_conversation (conversation_id,created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
