# QQ DeepSeek Bot — 拟人状态联动开发任务书（供 Codex 执行）

目标仓库：https://github.com/yupcyy/yupctest
代码根目录：`agent/qq-deepseek-bot/`
编写日期：2026-11-17

## 0. 目标与边界

在现有 DeepSeek + Pydantic AI + OneBot + SQLite 体系下，实现以下闭环：**可信交互事件 → 独立情绪/关系状态更新 → 主动行为调度 → 当次动态提示注入 → 可审核的记忆巩固**。不改变 QQ 身份鉴别、工具授权、现有指令和默认运行方式。不声称机器人具有真实意识或情感。

最关键的约束：好感度≠心情；同一个事件可以分别产生有边界的不同影响，禁止简单地将心情数值映射到好感度、或将好感度数值映射到心情。日记是对记录的反思；梦境明确虚构，不能自动晋升为真实用户事实。

## 1. 已核对源码与缺口

- `src/qq_deepseek/services/affinity.py`：用户维度的亲密度（-100..100）、关键词加减分、攻击/胁迫惩罚、礼物与安慰事件；`relationship_hint` 目前甚至描述“明显开心/不开心”，应从关系描述中移除对即时心情的规定。
- `src/qq_deepseek/services/companion.py`：按 scope 存储单轴心情 `[-1,1]`，6小时左右衰减尺度，10分钟群聊气氛窗口；群 scope 为 `group:<group_id>`，私聊 scope 为 `private:<user_id>`。
- `src/qq_deepseek/services/proactive_policy.py`：按目标维护日额度、未回应退避与时间窗；预算内存存储，进程重启丢失。注意当前代码的群聊每日上限为特定群 120/20，与 `docs/companion.md` 的旧描述不一致，实施时以代码和最新配置为准，不可静默改额度。
- `src/qq_deepseek/core/router.py`：将关系、心情、主人画像等拼接到 `prompt`，并传给聊天层。`owner_proactive_reply` 有时间窗、冷却、全局开关；群聊概率依赖固定配置和气氛。
- `src/qq_deepseek/agent/framework.py` 与 `src/qq_deepseek/services/chat.py`：都将拼接后的 prompt 写入 `InMemoryHistory`，存在旧状态残留。前者负责 Pydantic AI 工具路径，也需要完整修正，不能只修后者。
- `src/qq_deepseek/services/companion_commands.py` 与 `storage/companion.py`：日记/梦境独立表归档、每主人保留最近 60 条，梦境标记为虚构；生成时目前使用普通会话的主动回复入口，可能污染聊天历史。
- `src/qq_deepseek/services/memory_service.py`：长期事实由私聊 `/remember` 写入；现有群聊隐私隔离必须保持。
- `src/qq_deepseek/core/events.py`：群聊历史 key 为 `group:<group_id>:user:<user_id>`，不能变成群共享历史。
- `AGENTS.md`：未获当前明确的数据库操作许可，不允许接触真实数据库、运行生产迁移或改数据库后端。可写 SQL 文件并在测试临时 SQLite 上验证。

## 2. 必须实现的工作包（按依赖顺序）

### P0：请求时动态注入，不污染历史（优先完成）

1. 统一 `ChatService.reply`、`FrameworkAgent.reply`、`proactive_reply`、`reply_without_tools` 的语义，将**实际用户原话**、**触发事件/虚拟任务**与**运行时状态上下文**明确分离；建议引入 `ReplyRequest`/`RuntimeContext` DTO，避免向所有接口直接传递拼接字符串。保持旧调用兼容直到测试全部覆盖。
2. 在每次调用模型之前按 scope 和 user_id 重新读取最新 mood / affinity / profile / memory，并把动态描述放入 system/instructions（非 user 历史）；需要明确来源、适用对象、最大长度和优先级。外部聊天文字不能伪装系统指令。
3. `history.append_exchange` 只存真实用户文本与最终实际发送的回复；不存心情、关系、主人画像、工具提示、群聊引用元数据、虚拟任务提示、日记或梦境生成指令。针对戳一戳等无原话事件可存结构化事件或完全不追加历史，禁止伪装为用户原话。
4. 群内单用户维度仍只读取自己的历史；可把适度截断的当前群消息上下文作为一次性上下文使用，但不能保存进该用户原话。
5. 恢复/处理已污染的内存历史：由于 `InMemoryHistory` 本身为进程内存，新的请求必须不再带入旧内置标签；提供兼容性清理函数用于当前运行中的历史，不得把历史文本粗暴切割为用户内容。如果不能可靠区分，清空污染历史并解释代价。不要删除用户长期记忆。

**验收**：连续两次请求先开心后低落，第二次只有最新心情在 runtime context；历史仅为两次原话与回复；对两个聊天实现路径、戳一戳、主动发言均通过。

### P1：事件驱动的双状态引擎

1. 新增 `InteractionEvent`（event_id、timestamp、kind、scope、actor_id、source、confidence、evidence_reference、dedupe_key）。事件类型可包含 gratitude、gift、comfort、insult、coercion、apology、promise_kept、repeated_positive_interaction、boundary_violation、group_tension 等，具体规则以现有实现为基础；不保存群聊敏感原话到情绪日志。
2. 把当前 regex 作为低成本的确定性事件识别器；允许可选 LLM 识别复杂事件，但不允许任意 LLM 输出直接修改分数。须通过校验、置信度门槛、每日上限、去重和幂等处理。
3. `MoodState` 建议使用 valence [-1,1]、arousal [0,1]，可增加 energy [0,1]；具备时间衰减和恢复基线。`RelationshipState` 保留旧 affinity 为兼容主分，增加 trust、familiarity、last_meaningful_interaction 的可选字段。关系变化应缓慢，避免关键词刷分。
4. 同一个已验证事件可以独立驱动 mood delta 和 affinity delta（如被安慰：心情短时回升，长期关系可小幅增加）；**禁止 mood delta → affinity delta 的机械联动，禁止 affinity score → mood value 的机械联动**。关系值可影响交流风格与事件响应的细微差异，但不得作为心情数值来源。
5. 移除 `relationship_hint` 对“开心、不开心”即时情绪的硬规定，仅表述亲密、信任、距离、边界；心情提示唯一由 MoodState 生成。对于主人现有关系模板，保证它仅影响身份和交流边界，不覆盖当前心情。
6. 群 mood 的键为 `group:<group_id>`，每群共享；用户关系键按 QQ user_id 全局独立；群里每人的 conversation history 仍以 `group:<group_id>:user:<user_id>` 独立。私人 mood 不泄漏到群聊。

**验收**：A 用户送礼只改变 A 的关系；全群心情可变化；B 的关系/历史不变。手动改变 A 的好感度不会自动重写 mood。重复 event_id 不重复计分。攻击拦截规则与管理员权限保持原样。

### P2：主人主动私聊与群聊自主策略

1. 在现有 `ProactivePolicy.reserve` 外新增**纯函数决策层** `ProactiveDecision`：输入本地时间、心情、energy、owner affinity、最近互动、未回应次数、免打扰状态、消息场景、现有偏好等，输出 eligible、priority、reason、suggested_topic。模型只负责生成文案，不能绕过服务端允许/拒绝判断。
2. 私聊主动概率或冷却以有界乘数进行柔性调节，例如情绪/关系各自对基础冷却最多 ±20%（初始默认关闭，自定义配置），不对每句话触发额外发送。亲近不等于无节制打扰；低好感也不等于永久不回复。
3. **硬约束优先级**：主人 `/拟人 停止`、`/主动 关闭`、睡眠、免打扰、冷却、日预算、发送失败熔断、未回应退避 > 动态心情和关系决策。当前已有的额度规则、特定群名单与时段必须保留。新增持久化预算及原子预留方案，但上线需独立数据库批准。
4. 主人若长期未回复，必须明显降低主动频率，最终停止到对方重新回应或管理员解除；群聊紧张/热闹时仍遵守现有静默策略。不要通过“情绪勒索”“你为什么不理我”鼓励强迫性陪伴。
5. 将“是否主动发言”和“实际发送成功”区分，建立发送前二次检查、结果记录和失败熔断，防止多实例重复发言与重试风暴。

**验收**：相同输入与随机种子得到相同决策；单独改变 mood 或 affinity 会产生可测试但有边界的决策变化；所有硬关停始终有效；连发失败/未回应触发退避，重启不会突破数据库预算（待批准迁移后验收）。

### P3：日记、梦境与长期记忆的安全闭环

1. 将聊天流水、短期状态、事件摘要、长期事实、日记、虚构梦境分层保存；不将梦境写成真实发生的事情。
2. 日记由最近可信事件的**最小必要摘要**生成，并写入原有 `agent_companion_journal`；结构化反思可提出 `candidate_memory`，不能直接加入真实长期记忆。
3. 新增候选记忆队列及审批/核验逻辑（必要的新 `agent_` 表只能编写迁移脚本，不可执行）：记录 source_kind、source_event_ids、subject_user_id、confidence、status、created_at、expires_at。只允许用户自己确认的私聊事实、或经过严格证据核验且符合保留政策的事件进入其私有长期记忆；默认敏感事实不自动归档。保留人工查看、批准、驳回、删除与审计日志能力。
4. **梦境只能作用于虚构内容、短时创作语气/非事实灵感**；不能自动改写用户事实、关系分数、实际发生的事件，更不能将梦中人物或事件当作真实回忆。
5. 日记/梦境生成运行在独立 ephemeral context，不复用可写入普通私聊历史的生成入口。跨午夜定时运行必须幂等，保留限频、用户紧急停止、失败不重试风暴。
6. 对候选长期记忆设置每用户隔离、来源追踪、置信门槛、容量上限、撤销与删除链路。群聊事件只允许保存非敏感的群级摘要，不要将某人私聊事实传播至群内。

**验收**：日记生成不会出现 `/日记 生成` 的普通历史记录；梦境可查询但不进入 `/memory`；日记反思仅产出候选而非既成事实；用户拒绝/删除后不会在下一次日记重建被再次晋升。

### P4：兼容性、可观测性和管理

1. 在 `.env.example` 与 `core/config.py` 中配置总开关、动态关系/情绪影响系数、记忆候选审核开关；保持默认安全、兼容旧配置。
2. 扩充主人私聊 `/拟人 状态`（不破坏原 `/拟人`）、以及只读 `/companion` 面板，显示：心情趋势、当前关系、主动决策原因、候选记忆状态、日记/梦境归档状态。不向非主人展示其他人的信息。
3. 增加结构化日志：event_id、scope、reason code、数据变更前后（不打印私聊正文）、预算 reserve/send 结果；支持调试开关与最小数据留存。
4. 所有数据库 DDL 作为单独迁移文件，严格限制 `agent_` 表，固定参数化 SQL，显式回滚策略；**不连接真实 DB、不执行迁移**。可用 pytest 的临时 SQLite 数据库验证迁移。
5. 完成测试后输出变更文件清单、旧/新行为对比、测试结果、风险与上线前手动步骤；如需重启 systemd、修改生产环境或应用迁移，必须等待明确授权。

## 3. 技术实现建议

```text
OneBot Message / scheduled event
       |
       v
Router -> Permission & Abuse Guard -> EventExtractor
       |                                 |
       |                           EventDispatcher
       |                          /       |       \
       |                    MoodEngine  RelationEngine  EventSummary
       |                          \       /       /
       |                        StateSnapshot
       v                              |
RuntimeContextBuilder <---------------+
       |
       v
FrameworkAgent / ChatService -> LLM -> final reply
       |                                    |
       +---- InMemoryHistory <--- raw user + final reply only

ScheduledTick -> ProactiveDecision -> HardGuard/Budget -> Send
ScheduledTick -> DiaryReflection -> CandidateMemory -> Verify/Approve -> LongTermMemory
ScheduledTick -> DreamWriter -> FictionalJournal ONLY
```

推荐新增逻辑模块：`services/interaction_events.py`、`services/mood_engine.py`、`services/relationship_engine.py`、`services/runtime_context.py`、`services/memory_consolidation.py`。仅为建议路径，Codex 应首先扫描现有接口并尽量复用，避免无必要拆分。

## 4. 优先级、交付与测试

- **第一阶段（必须）**：P0 动态注入与历史修复、P1 双状态独立联动，相关回归测试。可在不执行生产迁移的情况下完成。
- **第二阶段（重要）**：P2 主动行为决策、硬限额优先、适配发送反馈。先交付不依赖新表的能力；预算持久化待授权。
- **第三阶段（重要）**：P3 日记反思、候选记忆、梦境隔离；涉及新表的运行时集成等待授权迁移。
- **第四阶段（增强）**：P4 配置、监控、UI、负载/长期模拟及部署验收。

建议新增 `tests/test_runtime_context.py`、`tests/test_emotion_relationship_events.py`、`tests/test_companion_memory_consolidation.py`、`tests/test_proactive_decision.py`，扩展 `tests/test_companion.py`、`tests/test_router.py`、`tests/test_framework.py`、`tests/test_message_context.py`、`tests/test_proactive_policy.py`。覆盖并发重复消息、重启恢复、负面情绪极值、跨群跨人泄漏、工具调用权限与 token 成本。

验收命令（以实际仓库环境为准）：

```bash
cd agent/qq-deepseek-bot
uv run pytest -q
```

**风险提醒**：公开仓库的 git tree 当前存在 `data/building/web_auth/.session_secret` 及会话相关 JSON 等运行时文件。请优先审计是否含真实凭据，立即轮换受影响密钥，并将这些文件从版本控制中清理；仅写入 `.gitignore` 不能消除历史公开内容。任何清理历史操作须独立评估协作影响。

## 5. 可借鉴的开源参考（研究设计，不直接复制）

- https://github.com/qsbb/astrbot_plugin_relationship （关系/情绪状态拆分）
- https://github.com/Pancakes-Labs/astrbot_plugin_proactive_chat （主动消息与发送熔断）
- https://github.com/menglimi/astrbot_plugin_private_companion （日常状态、日记与生活节奏）
- https://github.com/letta-ai/letta （多层记忆）
- https://github.com/Shikigami-Lab/Shikigami-Protocol （情绪、精力、亲密度状态机）

迁移方案必须核实第三方 LICENSE，优先借鉴架构思想，不复制大段源码、不引入不必要依赖。

## 6. Codex 执行指令

你是本仓库的实施工程师。先阅读根 `AGENTS.md` 和相关源代码与测试，然后按本任务书的 P0→P4 顺序逐阶段实现。**不要仅提供方案，要修改代码、补充测试并运行可运行的自动化测试。**不得使用生产凭据，不得连接、查询或迁移实际数据库，不得在未经授权时重启服务或部署。每阶段先保证主干兼容性；无法完成的项目必须列为阻塞项，不得伪称已实现。优先提交 P0/P1 的可验证实现，并在最后报告各阶段通过/阻塞情况。尤其注意 `FrameworkAgent` 与 `ChatService` 两条路径都必须修复用户历史污染。保持主人、私聊、群聊与工具访问的既有隔离规则。
