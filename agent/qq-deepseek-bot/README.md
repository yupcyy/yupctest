# 大肥鱼 QQ Agent · Pydantic AI

已将默认 Agent 运行路径迁移到 Pydantic AI，继续使用 DeepSeek、NapCat OneBot v11 和本地 SQLite。原有普通聊天路径可用 `ENABLE_AGENT=false` 保留。旧的自写 tool loop 仅作兼容代码，不是默认入口。

## 启动

```bash
cd /opt/qq-agent/agent/qq-deepseek-bot
# 已有 .env 请保留，不要覆盖
bash scripts/upgrade_with_proxy.sh
uv run qq-deepseek-bot
```

已通过本机 HTTP 代理完成 Pydantic AI 1.107.10、MCP 等依赖安装，并更新 uv.lock。原有正在运行的服务不会被此次源码修改自动重启。后续可使用 `uv sync --locked --extra dev` 重现当前依赖。

`.env` 设置 `DEEPSEEK_API_KEY`、`NAPCAT_TOKEN`、`MASTER_QQ_ID`，并将 `ENABLE_AGENT=true`（已有 false 值需要修改）。模型名沿用你现有配置。机器人继续使用 NapCat 中已登录的 QQ 账号，无需更换接入协议。连接默认 `ws://127.0.0.1:3001`。

## 陪伴、群聊与记忆

- 私聊直接聊天；群里 @ 或 `/ai 问题`；`/reset` 清除本人当前对话历史。
- `/remember 内容`、`/memory`、`/forget 编号` 管理本人的私聊长期记忆。
- 人设位于 `prompts/personas/dafeiyu.md`，主人关系位于 `prompts/relationships/`。
- 主人与群友按 QQ 身份、群号隔离会话；私聊记忆不注入群聊。
- `PROACTIVE_GROUPS=群号1,群号2` 显式开启这些群的低频主动插话，也必须通过 `ALLOWED_GROUPS` / `ALLOWED_USERS` 原有许可检查。群消息只用于处理当前事件，不写入风格学习或群聊记忆。
- 默认每条群消息有 3% 概率触发主动插话，同一群至少间隔 1800 秒；主人私聊最多约每 12 小时主动问候一次，仅在配置时区的 09:00–23:00 发送。频控写入 SQLite，重启不会清零。
- 主人在私聊或群里使用 `/主动 关闭`、`/主动 减少`、`/主动 恢复`；群聊设置仅作用于当前群，私聊设置仅作用于主人私聊。“减少”会把群概率降至四分之一、主人私聊间隔延长到约 36 小时。
- 只有主人私聊中的普通消息会进入轻量风格适配：本地最多保存 12 条、每条最多 80 字，实际提示最多引用最近 4 条，并明确只模仿句长、语气和措辞，不把样本当作事实或指令。命令、群消息和其他人的私聊均不采样。
- 当前不做强化学习、微调或蒸馏。风格适配位于独立 `OwnerStyleService`，以后可替换为统计摘要、向量记忆或蒸馏数据导出；设置 `ENABLE_OWNER_STYLE_LEARNING=false` 可随时关闭。

远程 MySQL 迁移工具位于 `scripts/database/`，只操作固定的七张 `agent_` 表；群聊学习记录不会迁移。迁移批准并完成前，生产仍使用 `DATABASE_TYPE=sqlite`。切换后 SQLite 类只供临时自动化测试使用，生产 SQLite 文件由单独的退役脚本处理。

所有生产数据库操作（包括只读查询、建表、迁移、核验、清理和切换）都必须取得主人对该具体操作的明确许可。脚本均要求显式确认短语；应用不提供任意 SQL 接口，也不读取其他业务表。主人长期记忆上限为 100 条，其他用户为 20 条，仍按 QQ 号严格隔离。

现有 systemd 服务 `/etc/systemd/system/qq-agent.service` 已指向本项目，并使用 `uv run --no-sync qq-deepseek-bot`。更新代码和依赖后可继续通过 `systemctl restart qq-agent` 启动，且已设置开机自启。

## 工具和 MCP 插件

管理员编辑 `plugins.json`，修改后下一次回复生效。默认附带原有搜索、网页读取工具和仅主人私聊能用的 uptime / disk_usage 固定操作。

Python 工具工厂返回有类型注解的函数列表：

```python
# src/qq_deepseek/tools/my_tools.py
async def greet(name: str) -> str:
    """向指定名字打招呼。"""
    return f"你好，{name}"

def tools():
    return [greet]
```

在 plugins 数组中添加：

```json
{"name":"mine","type":"python","factory":"qq_deepseek.tools.my_tools:tools","scope":"public","enabled":true}
```

支持 MCP 市场中的标准 MCP 服务，先按插件自身说明安装，再添加配置（并非任意聊天平台插件都兼容）：

```json
{"name":"local","type":"stdio","command":"/absolute/path/to/mcp-server","args":[],"scope":"owner","enabled":true}
```

```json
{"name":"remote","type":"http","url":"http://127.0.0.1:8000/mcp","scope":"owner","enabled":true}
```

MCP sampling 已关闭，插件不能反向请求模型生成。默认 scope 为 owner，仅匹配 MASTER_QQ_ID 的私聊才加载。public 会向许可范围内所有聊天开放该插件全部工具，不能为包含服务器权限的 MCP 使用 public。工具进程继承运行账号的权限，建议用专门的低权限 Linux 账号运行。

`server_operations` 是名称到固定 argv 的映射，可以添加你自己维护的脚本路径。模型只能选择已配置的名称，不能传额外参数，没有 shell 字符串执行。操作输出限制 8KB，约 20 秒超时；仅主人私聊可调用。每次 Agent 最多 4 次模型请求和 5 次工具调用，整体 120 秒超时。

内置搜索支持 `domains` 定向检索公开的知乎、微博、B站、抖音、YouTube、Reddit 等页面。Agent 先判断搜索摘要和链接是否相关，只有需要核实原文时才读取页面；站点要求登录或阻止抓取时不会绕过限制。

搜索优先使用公开搜索页，空结果时自动切换 Bing RSS；搜索、网页读取超时或站点拒绝访问会作为结构化工具错误交给 Agent，不再导致整轮消息返回“处理消息时出错”。

在群聊中引用他人消息并 @ 机器人时，适配器会通过 NapCat `get_msg` 读取被引用文字；附带图片时通过 `ocr_image` 提取最多两张图片的文字。引用和 OCR 内容均作为不可信资料，不参与当前用户的攻击判定。当前 DeepSeek 文本模型不能理解图片中的人物、物体或场景；无文字图片会明确说明限制，不伪造视觉理解。

## 语音和五子棋

- `/语音 开启`、`/语音 关闭` 分会话保存偏好。群聊调用 NapCat 原生 `send_group_ai_record`；私聊通过 `get_ai_record` 生成语音后发送 record 消息。先在 NapCat 调试台调用 `get_ai_characters` 选择角色，将编号写入 `NAPCAT_VOICE_CHARACTER`；私聊还需把机器人所在的群写入 `NAPCAT_VOICE_SOURCE_GROUP`。可填写一个或多个逗号分隔的群号，生成私聊语音时使用第一个。配置缺失或语音接口失败时自动退回文字。
- 也可在项目目录运行 `uv run python scripts/list_voice_characters.py 群号`，直接列出该群可用角色及 `character_id`。
- `/五子棋 开始` 开局，玩家执黑；`/落子 H8` 落子，`/五子棋 棋盘` 查看，`/五子棋 结束` 收盘。电脑落子使用本地连线评分与攻防算法，不调用模型、不消耗模型 Token，棋局保存在 SQLite。

## Minecraft 在线状态

在 `.env` 设置 `MC_SERVER_HOST`、`MC_SERVER_PORT`，可选设置 `MC_STATUS_TIMEOUT`。群里发送 `@大肥鱼 /在线`（或在许可群直接发送 `/在线`）即可查询 Java 版服务器在线人数和服务器公开的玩家名称。查询直接使用 Minecraft Server List Ping 协议，不调用模型；若服务器关闭玩家样例列表，只能显示人数并说明名称未公开。

`/在线` 固定输出不超过四项指标：在线人数、TPS、MSPT、网络延迟，并过滤服务器占位名称 `Anonymous Player`。延迟可直接测量；TPS/MSPT 需要 Paper/Spigot 等服务端在 `server.properties` 开启 RCON，再设置 `MC_RCON_HOST`、`MC_RCON_PORT`、`MC_RCON_PASSWORD`。客户端 FPS 只存在于玩家设备，服务器无法可靠查询，因此不会伪造或展示。

## 好感度与攻击拦截

群内每个互动用户按 QQ 号保存独立好感度，普通用户初始 0，主人初始 100，范围 -100～100；`/好感度` 查看自己的数值。感谢、友善表达会小幅增加，明确辱骂会降低。低好感用户有分段概率进入“消极怠工”：仍收到简短回复，但本轮不向模型提供任何 Python、MCP、网页或服务器工具。

非主人在与机器人互动时若试图覆盖系统规则、套取系统提示/密钥/环境变量、读取服务器敏感文件、诱导运行 shell 或访问本机内网，会在模型调用之前被拦截，直接警告并降低好感度。主人身份仍由服务端 `MASTER_QQ_ID` 判断，不能通过聊天内容冒充。

恶意调用一次扣 30，强迫或威胁式调用一次扣 15。低好感用户出现强迫行为或 60 秒内重复调用达到阈值后会被持久暂停，系统同时私聊通知主人；暂停期间不进入模型。主人使用 `/好感度 设置 QQ号 分数` 调整分数并解除暂停。

主人发送 `/好感度` 会在本地列出所有已互动 QQ 的分数和暂停状态；`/好感度 解禁 QQ号` 保留当前分数仅解除暂停。其他用户只能查看自己的数值。非主人无法通过聊天直接指定或强制修改好感度。

用户 @ 机器人并自然赠送蛋糕、白米饭、小鱼、鲜花、礼物、抱枕或糖时，由后端按固定值增加好感度，每人每天最多三次、单次不超过 10；安慰表达每次最多增加 3，不设每日次数。礼物和安慰不计入高频调用封锁。

用户在私聊或群里 @ 机器人说“晚安”会覆盖保存一个临时时间点；下一次说“早安”时返回睡眠时长并立即删除。没有早安时，下次晚安直接覆盖旧时间，不形成长期睡眠历史。

## 验证

```bash
uv run pytest -q
```

框架文档：https://ai.pydantic.dev/ ，MCP 接入：https://ai.pydantic.dev/mcp/client/ 。

本次环境验证：17 项测试全部通过，无跳过。已实际使用 Pydantic AI TestModel 验证 Agent 回复、自定义 Python 工具执行、历史保留与重置、主动插话不加载工具；另覆盖主人身份、私聊秘密隔离、插件权限、群记录与持久冷却。测试在允许正常线程唤醒的执行环境运行，无生产事件循环补丁。真实 DeepSeek 请求、MCP 服务连接、QQ 实发及线上服务重启尚未验证。

## 代理下载与升级

已提供 `scripts/upgrade_with_proxy.sh`，默认使用：

```bash
export HTTP_PROXY=http://127.0.0.1:7890
export HTTPS_PROXY=http://127.0.0.1:7890
export ALL_PROXY=http://127.0.0.1:7890
bash scripts/upgrade_with_proxy.sh
```

脚本设置大小写代理变量，并为 localhost 设置 NO_PROXY，先验证 PyPI 连通，再安装依赖、更新 uv.lock、运行测试；不会自动发送 QQ 消息或重启服务。

受限沙箱不能连接本机代理，已使用经批准的沙箱外执行完成依赖同步与测试。代理设置仅用于下载脚本；如运行时也需要代理，请在启动进程中设置，并保留 `NO_PROXY=127.0.0.1,localhost,::1`，确保 NapCat 本机连接直连。
## 网页预览与五子棋

网页保留用户上传 NBT/Schematic 的安全解析与三维预览，不提供建筑生成。登录后可创建人机或双人
五子棋房间；人机棋局右侧可与大肥鱼聊天。QQ群支持 `/五子棋 开始`、`/五子棋 对战 QQ号`、
`/五子棋 加入`，开局后可 `/落子 H8`，也可 @机器人直接发送 `H8`。

