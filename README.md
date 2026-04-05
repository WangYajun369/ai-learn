# MCP + Skills 销售分析 Agent

一个基于 MCP（Model Context Protocol）的 AI Agent 示例项目，演示如何通过 **MCP 工具 + Skills 技能包** 构建一个具备"专家级分析能力"的智能助手。

## 架构

```
用户（自然语言）
    ↓
agent.py（MCP Client + Skill Engine + LLM Backend + 向量记忆 + 会话记录）
    ↓ stdio                                    ↕ ChromaDB          ↕ SQLite
server.py（MCP Server — 销售数据工具集）     memory_db/（长期记忆） conversations.db（会话记录）
    ↓
sales.db（SQLite 销售数据库）
```

### 长期记忆（向量数据库）

基于 ChromaDB 的语义向量记忆系统，支持跨会话记忆持久化：

- **自动保存**：对话结束（exit/quit）时，LLM 自动提取对话摘要存入向量库
- **自动检索**：每轮对话前，根据用户输入语义检索相关的历史记忆注入 system prompt
- **手动管理**：通过 `/memory` 命令查看、搜索、清空记忆
- **存储位置**：`./memory_db/`（ChromaDB 持久化目录）

```
memory_db/                  # ChromaDB 持久化目录（自动创建）
├── chroma.sqlite3          # 元数据存储
└── ...                     # 向量索引文件
```

| 命令 | 说明 |
|------|------|
| `/memory list` | 列出最近 10 条记忆 |
| `/memory search <关键词>` | 语义搜索相关记忆 |
| `/memory clear` | 清空所有记忆 |
| `/memory stats` | 查看记忆统计信息 |

### 会话记录（SQLite）

基于 SQLite 的完整会话历史记录，每次启动自动创建新会话：

- **自动记录**：实时保存用户问题、Agent 回复、工具调用链（含耗时）
- **会话管理**：启动自动创建新会话，退出自动关闭并统计轮次
- **调用链追踪**：记录每次工具调用的名称、参数、返回结果、耗时（ms）
- **存储位置**：`./conversations.db`（SQLite WAL 模式）

```
conversations.db            # 会话记录数据库（运行后自动创建）
├── sessions                # 会话元信息（ID、模型、时间、轮次、状态）
├── messages                # 问答记录（用户问题 + Agent 回复）
└── tool_calls              # 工具调用链（名称、参数、结果、耗时）
```

| 命令 | 说明 |
|------|------|
| `/history` | 列出最近 10 个会话 |
| `/history show <会话ID>` | 查看会话详情（完整对话 + 工具调用链） |
| `/history stats` | 查看会话统计信息 |

### Skill 包结构（渐进式加载）

```
sales-analysis/
├── SKILL.md              # 核心大脑：元数据 + 执行流程 + 输出规范
├── scripts/
│   ├── calculate_metrics.py   # 指标计算（仅结果返回，代码不进上下文）
│   └── detect_anomaly.py      # 异常检测
└── references/
    └── report_template.md     # 报告输出模板
```

**渐进式加载**：
1. **启动时**（~100 tokens）：仅加载 SKILL.md 的 name + description，用于技能路由
2. **匹配时**（<5000 tokens）：加载完整 SKILL.md 指令，解析业务 SOP
3. **执行时**（按需）：加载 scripts/ 或 references/，代码不暴露给模型

## 快速开始

```bash
# 安装依赖
uv sync

# 初始化销售数据库
uv run init_db.py

# 运行 Agent（默认终端 REPL 模式）
uv run agent.py

# 或使用 TUI 界面（可选）
uv run agent.py --tui
```

### 运行示例

启动后，你可以尝试以下对话：

```
👤 你：分析华东区的销售表现
📦 匹配到技能包：sales-analysis
   ✅ 技能指令已加载（完整 SKILL.md）
   ✅ 报告模板已加载（references/report_template.md）
🔧 调用工具：query_sales_by_region({"region": "华东"})...
🤖 Agent：📊 华东区销售分析报告
         总销售额：¥1,084,000.00
         ...
```

```
👤 你：有哪些产品
🔧 调用工具：list_products({})...
🤖 Agent：📦 产品列表
         1. AI 助手基础版
         2. AI 助手企业版
         ...
```

```
👤 你：/history show 20260404_203500
══════════════════════════════════════════════════════
  会话 [20260404_203500]  模型：qwen-max
  📅 2026-04-04T20:35:00 → 2026-04-04T20:38:00
  💬 3 轮对话
══════════════════════════════════════════════════════

📝 对话记录：
  👤 用户：分析华东区的销售表现
  🤖 Agent：📊 华东区销售分析报告...

🔧 工具调用链（2 次）：
  → query_sales_by_region({"region": "华东"})  ⏱ 45ms
    返回：[{"product": "AI 助手基础版", "month": "4月", "sales": 45000}, ...]
  → query_sales_by_region({"region": "华南"})  ⏱ 32ms
    返回：[{"product": "AI 助手基础版", "month": "4月", "sales": 38000}, ...]
══════════════════════════════════════════════════════
```

## MCP 工具列表

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `list_products` | 查询所有产品列表 | 无 |
| `query_sales_by_product` | 按产品查询销售数据 | product_name |
| `query_sales_by_region` | 按区域查询销售数据 | region |
| `get_sales_overview` | 全局销售概览 | 无 |
| `get_raw_sales_data` | 获取原始 JSON 数据（供脚本分析） | product_name?, region? |

## 支持的模型后端

- **通义千问 qwen-max**（DashScope）
- **智谱 GLM-4.5-Air**（BigModel）

## 环境变量

在 `.env` 文件中配置：

```env
DASHSCOPE_API_KEY=sk-xxx
BIGMODEL_API_KEY=xxx
```

## 项目文件

| 文件 | 说明 |
|------|------|
| `agent.py` | Agent 核心逻辑（MCP Client + Skill Engine + 向量记忆 + 会话记录） |
| `tui.py` | TUI 界面（基于 Textual 框架，通过 `--tui` 启动） |
| `server.py` | MCP Server（5 个销售数据工具） |
| `memory_store.py` | 向量记忆模块（ChromaDB 封装） |
| `conversation_store.py` | 会话记录模块（SQLite 封装，含工具调用链） |
| `init_db.py` | 销售数据库初始化脚本 |
| `sales-analysis/` | Skill 技能包（SKILL.md + scripts/ + references/） |
| `object_db/` | 数据库统一存储目录（运行后自动创建） |
