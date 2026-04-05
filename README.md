# MCP + Skills 销售分析 Agent

一个基于 MCP（Model Context Protocol）的 AI Agent 示例项目，演示如何通过 **MCP 工具 + Skills 技能包** 构建具备"专家级分析能力"的智能助手。

## ✨ 核心特性

- **🔧 MCP 工具调用**：基于 FastMCP 实现标准化工具协议，支持多步工具链调用
- **📦 渐进式 Skill 加载**：三阶段按需加载（摘要→完整指令→脚本/模板），最小化 Token 消耗
- **🧠 双层记忆系统**：
  - **向量记忆**（ChromaDB）：跨会话语义检索，自动摘要存储
  - **会话记录**（SQLite）：完整对话回溯，工具调用链追踪（含耗时）
- **🤖 多模型支持**：通义千问、智谱 GLM、Ollama 本地模型，统一后端抽象接口
- **💻 双模式界面**：REPL 终端模式 + Textual TUI 图形界面

## 🏗️ 架构

```
用户终端（自然语言）
    ↓
agent.py（MCP Client + Skill Engine + LLM Backend + 向量记忆 + 会话记录）
    ↓ stdio                                    ↕ ChromaDB          ↕ SQLite
server.py（MCP Server — 5 个销售数据工具）     memory_db/（长期记忆） conversations.db（会话记录）
    ↓
sales.db（SQLite — 52 条 Q2 销售记录）
```

### 长期记忆（向量数据库）

基于 ChromaDB 的语义向量记忆系统，支持跨会话记忆持久化：

- **自动保存**：对话结束（`/exit` 或 `Ctrl+C`）时，LLM 自动提取对话摘要存入向量库
- **自动检索**：每轮对话前，根据用户输入语义检索相关历史记忆注入 system prompt
- **手动管理**：通过 `/memory` 命令查看、搜索、清空记忆
- **存储位置**：`./object_db/memory_db/`（ChromaDB 持久化目录）

| 命令 | 说明 |
|------|------|
| `/memory list` | 列出最近 10 条记忆 |
| `/memory search <关键词>` | 语义搜索相关记忆 |
| `/memory delete <记忆ID>` | 删除指定记忆 |
| `/memory clear` | 清空所有记忆 |
| `/memory stats` | 查看记忆统计信息 |

### 会话记录（SQLite）

基于 SQLite 的完整会话历史记录：

- **自动记录**：实时保存用户问题、Agent 回复、工具调用链（含耗时）
- **会话管理**：启动自动恢复上次会话，`/new` 创建新会话
- **调用链追踪**：记录每次工具调用的名称、参数、返回结果、耗时（ms）
- **存储位置**：`./object_db/conversations.db`（SQLite WAL 模式）

| 命令 | 说明 |
|------|------|
| `/history` | 列出最近 10 个会话 |
| `/history show <会话ID>` | 查看会话详情（完整对话 + 工具调用链） |
| `/history resume <会话ID>` | 恢复到指定会话继续对话 |
| `/history delete <会话ID>` | 删除指定会话 |
| `/history clear` | 清空所有会话记录 |
| `/history stats` | 查看会话统计信息 |

### Skill 包结构（渐进式加载）

```
sales-analysis/
├── SKILL.md              # 核心大脑：元数据 + 执行流程 + 输出规范
├── scripts/
│   ├── calculate_metrics.py   # 指标计算（增长率/客单价/区域占比）
│   └── detect_anomaly.py      # 异常检测（Z-score/区域差异/波动率）
└── references/
    └── report_template.md     # 标准报告输出模板
```

**渐进式加载机制**：
1. **启动时**（~100 tokens）：仅加载 SKILL.md 的 name + description，用于技能路由
2. **匹配时**（<5000 tokens）：加载完整 SKILL.md 指令，解析业务 SOP
3. **执行时**（按需）：加载 scripts/ 或 references/，代码不暴露给模型上下文

## 🚀 快速开始

### 环境准备

```bash
# 安装依赖（使用 uv）
uv sync

# 配置 API Key
cp .env.example .env
# 编辑 .env 文件，填入你的 API Key
```

### 运行

```bash
# 初始化销售数据库（52 条 Q2 测试数据）
uv run init_db.py

# 启动 Agent（默认 REPL 模式，交互式选择模型）
uv run agent.py

# 或使用 TUI 界面
uv run agent.py --tui

# 单独运行 MCP Server（测试用）
uv run server.py
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
         成交笔数：42 笔
         平均客单价：¥25,809.52
         ...
```

```
👤 你：有哪些产品
🔧 调用工具：list_products({})...
🤖 Agent：📦 产品列表
         1. AI 助手基础版
         2. AI 助手专业版
         3. AI 助手企业版
         4. 数据分析模块
         5. 智能客服模块
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

## 🔧 MCP 工具列表

| 工具名 | 功能 | 参数 |
|--------|------|------|
| `list_products` | 查询所有产品列表 | 无 |
| `query_sales_by_product` | 按产品查询销售数据（支持模糊匹配） | `product_name` |
| `query_sales_by_region` | 按区域查询销售数据（支持模糊匹配） | `region` |
| `get_sales_overview` | 全局销售概览 | 无 |
| `get_raw_sales_data` | 获取原始 JSON 数据（供脚本分析） | `product_name?`, `region?` |

## 🤖 支持的模型后端

| 后端 | 模型 | 环境变量 |
|------|------|----------|
| **通义千问** | qwen-max / qwen-plus / qwen-turbo | `DASHSCOPE_API_KEY` |
| **智谱 GLM** | GLM-4.5-Air / GLM-4-Flash | `BIGMODEL_API_KEY` |
| **Ollama** | qwen2.5:7b / llama3.2 等本地模型 | `OLLAMA_BASE_URL`, `OLLAMA_MODEL` |

### Ollama 本地模型配置

```env
# .env 文件
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b
```

确保本地已启动 Ollama 服务并拉取模型：
```bash
ollama pull qwen2.5:7b
ollama serve
```

## ⚙️ 环境变量

在 `.env` 文件中配置：

```env
# 通义千问（阿里云 DashScope）
DASHSCOPE_API_KEY=sk-xxx

# 智谱 GLM（BigModel）
BIGMODEL_API_KEY=xxx

# Ollama 本地模型（可选）
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5:7b
```

## 📁 项目结构

```
.
├── agent.py                 # 入口：模型选择、AgentCore 初始化
├── agent/
│   ├── core.py             # Agent 核心：对话循环、工具调用、流式输出
│   ├── skill_loader.py     # 渐进式 Skill 加载器
│   ├── backends/           # LLM 后端实现
│   │   ├── base.py         # 统一后端抽象接口
│   │   ├── qwen.py         # 通义千问后端
│   │   ├── glm.py          # 智谱 GLM 后端
│   │   └── ollama.py       # Ollama 本地模型后端
│   └── commands/           # 斜杠命令处理器
│       ├── memory.py       # /memory 命令
│       └── history.py      # /history 命令
├── server.py               # MCP Server（FastMCP，5 个销售工具）
├── memory_store.py         # ChromaDB 向量记忆封装
├── conversation_store.py   # SQLite 会话记录封装
├── init_db.py              # 销售数据库初始化（52 条测试数据）
├── sales-analysis/         # Skill 技能包
│   ├── SKILL.md            # 技能定义（元数据 + 执行流程 + 输出规范）
│   ├── scripts/            # 分析脚本（指标计算、异常检测）
│   └── references/         # 参考文件（报告模板）
├── object_db/              # 数据库统一存储目录（运行后自动创建）
│   ├── sales.db            # 销售业务数据
│   ├── memory_db/          # ChromaDB 向量记忆持久化
│   └── conversations.db    # 会话记录与工具调用链
├── pyproject.toml          # 项目依赖配置
└── README.md               # 本文件
```

## 📝 斜杠命令

| 命令 | 说明 |
|------|------|
| `/new` | 创建新会话 |
| `/memory list/search/delete/clear/stats` | 记忆管理 |
| `/history [show/resume/delete/clear/stats]` | 会话记录管理 |
| `/help` | 显示所有命令 |
| `/exit` | 退出程序 |

## 🔑 关键设计模式

### 渐进式 Skill 加载
最小化 Token 成本，三阶段按需加载：
- **阶段 1**：启动时仅加载 name + description（~100 tokens）用于路由
- **阶段 2**：匹配后加载完整 SKILL.md（<5000 tokens）解析业务 SOP
- **阶段 3**：执行时按需加载 scripts/ 或 references/，代码不暴露给模型

### Backend 抽象层
统一接口 `BaseBackend`（`agent/backends/base.py`）：
- `build_tools()` - 将 MCP 工具转换为后端特定格式
- `chat()` / `chat_stream()` - 同步/流式对话
- `make_tool_call_raw_message()` / `make_tool_result_message()` - 工具调用消息构造

### Skill-Tool 协同
SKILL.md 定义业务流程和工具调用顺序，scripts/ 负责计算逻辑，references/ 提供输出模板。

## 📄 License

[MIT](LICENSE)
