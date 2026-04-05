# MCP + Skills 销售分析 Agent - 项目架构文档

> 本文档详细描述了项目的整体架构设计、核心组件、数据流和关键技术决策。

---

## 1. 架构概览

### 1.1 系统架构图

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              用户终端层                                       │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  REPL 交互界面  │  TUI 图形界面  │  斜杠命令 (/help, /memory, ...)   │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Agent 核心层 (Client)                           │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  agent.py                    # 入口：模型选择、AgentCore 初始化        │   │
│  │  agent/core.py               # 对话循环、工具调用、流式输出            │   │
│  │  agent/skill_loader.py       # 渐进式 Skill 加载器                   │   │
│  │  agent/backends/             # LLM 后端抽象层                        │   │
│  │    ├── base.py               # 统一后端接口定义                      │   │
│  │    ├── qwen.py               # 通义千问后端                          │   │
│  │    ├── glm.py                # 智谱 GLM 后端                         │   │
│  │    └── ollama.py             # Ollama 本地模型后端                   │   │
│  │  agent/commands/             # 斜杠命令处理器                        │   │
│  │    ├── memory.py             # /memory 命令                        │   │
│  │    └── history.py            # /history 命令                       │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓ stdio (MCP 协议)
┌─────────────────────────────────────────────────────────────────────────────┐
│                              MCP Server 层                                   │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  server.py                   # FastMCP Server，5 个销售数据工具       │   │
│  │    ├── list_products()       # 查询所有产品列表                     │   │
│  │    ├── query_sales_by_product()  # 按产品查询销售数据               │   │
│  │    ├── query_sales_by_region()   # 按区域查询销售数据               │   │
│  │    ├── get_sales_overview()      # 全局销售概览                     │   │
│  │    └── get_raw_sales_data()      # 获取原始 JSON 数据               │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓ SQL
┌─────────────────────────────────────────────────────────────────────────────┐
│                              数据存储层                                       │
│  ┌──────────────────┬──────────────────┬─────────────────────────────────┐  │
│  │  object_db/      │  object_db/      │  object_db/                     │  │
│  │  sales.db        │  memory_db/      │  conversations.db               │  │
│  │  (SQLite)        │  (ChromaDB)      │  (SQLite)                       │  │
│  │                  │                  │                                 │  │
│  │  销售业务数据     │  向量长期记忆     │  会话记录与工具调用链            │  │
│  │  52 条测试记录   │  语义检索         │  完整对话回溯                   │  │
│  └──────────────────┴──────────────────┴─────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
                                      ↓
┌─────────────────────────────────────────────────────────────────────────────┐
│                              Skill 技能包                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │  sales-analysis/                                                     │   │
│  │    ├── SKILL.md              # 技能定义（元数据 + 执行流程）          │   │
│  │    ├── scripts/                                                    │   │
│  │    │   ├── calculate_metrics.py   # 指标计算脚本                   │   │
│  │    │   └── detect_anomaly.py      # 异常检测脚本                   │   │
│  │    └── references/                                                 │   │
│  │        └── report_template.md   # 标准报告输出模板                 │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 核心设计原则

| 原则 | 说明 |
|------|------|
| **渐进式加载** | 最小化 Token 消耗，三阶段按需加载 Skill |
| **后端抽象** | 统一接口支持多模型（Qwen/GLM/Ollama） |
| **双层记忆** | 向量记忆（语义检索）+ SQLite（完整记录） |
| **工具协同** | SKILL.md 定义流程，scripts/ 负责计算逻辑 |

---

## 2. 核心组件详解

### 2.1 Agent 核心 (agent/core.py)

`AgentCore` 是整个系统的控制中心，负责：

- **对话循环管理**：主循环 `run_conversation_loop()` 处理用户输入
- **流式响应处理**：`process_streaming_response()` 实现实时输出
- **技能匹配**：`try_match_skill()` 根据关键词触发 Skill 加载
- **记忆注入**：`inject_memory()` 语义检索相关历史记忆
- **工具调用链**：多步工具调用支持（chain-of-thought）

**关键状态**：
```python
self.messages: list[dict]          # 对话消息历史
self.active_skill: dict | None     # 当前激活的技能包
self.turn_count: int               # 对话轮次计数
self.session_id: str               # 记忆会话 ID
self.conv_session_id: str          # 会话记录 ID
```

### 2.2 渐进式 Skill 加载 (agent/skill_loader.py)

三阶段加载策略，有效控制 Token 成本：

```
阶段 1: 启动时 (~100 tokens)
    └── 仅加载 SKILL.md 的 YAML 头部 (name + description + trigger_keywords)
    └── 用途：技能路由与快速匹配

阶段 2: 匹配时 (<5000 tokens)
    └── 加载完整 SKILL.md 指令内容
    └── 用途：解析业务 SOP、执行流程、输出规范

阶段 3: 执行时 (按需)
    └── 加载 scripts/ 或 references/ 中的文件
    └── 用途：代码执行、模板渲染（代码不暴露给模型上下文）
```

**安全设计**：
- 路径遍历防护：`get_script_path()` 检查 `..`、 `/`、 `\` 等危险字符
- 符号链接检查：确保解析后的路径仍在 scripts 目录内
- 文件类型限制：仅允许 `.py` 文件

### 2.3 LLM 后端抽象 (agent/backends/)

**BaseBackend** 定义统一接口：

| 方法 | 职责 |
|------|------|
| `check()` | 验证模型可用性 |
| `build_tools()` | MCP 工具 → 后端特定格式转换 |
| `chat()` | 非流式对话调用 |
| `chat_stream()` | 流式对话调用（实时输出） |
| `make_tool_call_raw_message()` | 工具调用消息构造 |
| `make_tool_result_message()` | 工具结果消息构造 |

**支持的后端**：
- **QwenBackend**: 阿里云 DashScope API（qwen-max/qwen-plus/qwen-turbo）
- **GLMBackend**: 智谱 BigModel API（GLM-4.5-Air/GLM-4-Flash）
- **OllamaBackend**: 本地模型服务（OpenAI 兼容接口）

### 2.4 双层记忆系统

#### 2.4.1 向量记忆 (memory_store.py)

基于 ChromaDB 的长期语义记忆：

- **自动保存**：对话结束时 LLM 提取摘要存入向量库
- **自动检索**：每轮对话前根据用户输入语义检索相关记忆
- **存储结构**：`{content, metadata: {session_id, timestamp, topics}}`
- **相似度度量**：余弦相似度（cosine）

**记忆生命周期**：
```
对话结束 → LLM 生成摘要 → 提取话题标签 → 存入 ChromaDB
                                    ↓
用户输入 ← 语义检索相关记忆 ← 注入 system prompt
```

#### 2.4.2 会话记录 (conversation_store.py)

基于 SQLite 的完整会话历史：

**表结构**：
```sql
sessions:      id, model, started_at, ended_at, turn_count, status
messages:      id, session_id, role, content, turn_order, created_at
tool_calls:    id, session_id, message_id, tool_name, arguments, result, duration_ms, created_at
```

**特性**：
- 会话恢复：启动时自动恢复上次会话上下文
- 工具调用链追踪：记录每次调用的名称、参数、结果、耗时（ms）
- WAL 模式：支持高并发读写

### 2.5 MCP Server (server.py)

FastMCP 实现的工具服务端，提供 5 个销售数据工具：

| 工具 | 功能 | 参数 |
|------|------|------|
| `list_products` | 查询所有产品列表 | 无 |
| `query_sales_by_product` | 按产品查询销售数据 | `product_name` |
| `query_sales_by_region` | 按区域查询销售数据 | `region` |
| `get_sales_overview` | 全局销售概览 | 无 |
| `get_raw_sales_data` | 获取原始 JSON 数据 | `product_name?`, `region?` |

**安全设计**：
- SQL 注入防护：参数化查询 + LIKE 特殊字符转义
- 输入验证：长度限制（product_name ≤100, region ≤50）
- 模糊匹配：支持去除空格匹配、LIKE 模糊查询

---

## 3. 数据流

### 3.1 正常对话流程

```
用户输入
    ↓
[AgentCore] 检索相关记忆 → 注入 system prompt
    ↓
[AgentCore] 技能匹配 → 加载完整 SKILL.md（如果匹配）
    ↓
[AgentCore] 发送消息到 LLM Backend
    ↓
[LLM Backend] 流式返回响应
    ↓
[AgentCore] 实时打印输出
    ↓
是否需要工具调用?
    ├── 是 → [MCP Server] 执行工具 → 返回结果 → 继续对话循环
    └── 否 → 记录回复 → 等待下一轮输入
```

### 3.2 工具调用链流程

```
用户："分析华东区的销售表现"
    ↓
Agent：匹配到 sales-analysis 技能包
    ↓
调用 query_sales_by_region({"region": "华东"})
    ↓
MCP Server 查询 SQLite → 返回销售数据
    ↓
Agent 将结果注入对话上下文
    ↓
LLM 分析数据 → 生成报告
    ↓
输出结构化分析报告
```

### 3.3 会话恢复流程

```
启动 Agent
    ↓
连接 SQLite 会话数据库
    ↓
查询最近会话
    ↓
是否有未关闭会话?
    ├── 是 → 恢复会话上下文 → 加载历史消息
    └── 否 → 创建新会话
```

---

## 4. Skill 包设计

### 4.1 SKILL.md 结构

```yaml
---
name: sales-analysis
description: 销售数据分析技能包描述
trigger_keywords: [销售分析, 业绩分析, ...]
requirements: [python3]
---

# 技能指令内容

## 角色设定
## 执行流程
## 输出规范
## 注意事项（护栏）
## 工具调用参考
```

### 4.2 技能执行流程

```
1. 解析用户意图
   └── 提取 product_name, region, time_range

2. 查询原始数据
   └── 根据参数调用相应 MCP 工具

3. 数据分析
   ├── 计算核心指标（总销售额、成交笔数、客单价）
   ├── 异常检测（区域集中度、销售额偏低等）
   └── 趋势判断（月度环比增长率）

4. 生成报告
   └── 严格按照 report_template.md 格式输出
```

### 4.3 护栏机制

- **数据缺失处理**：明确标注"暂无相关数据"，不猜测编造
- **数据脱敏**：不展示客户名单、订单号等敏感信息
- **预测声明**：趋势预测标注"基于历史数据，仅供参考"
- **人工确认**：涉及发送报告、调整策略等操作需用户确认

---

## 5. 扩展性设计

### 5.1 添加新模型后端

1. 继承 `BaseBackend`
2. 实现 6 个抽象方法
3. 在 `agent/backends/__init__.py` 注册

```python
class NewBackend(BaseBackend):
    def check(self) -> str | None: ...
    def build_tools(self, mcp_tools) -> list: ...
    def chat(self, messages, tools) -> dict: ...
    def chat_stream(self, messages, tools): ...
    def make_tool_call_raw_message(self, tool_calls, content): ...
    def make_tool_result_message(self, tool_call, result_text): ...
```

### 5.2 添加新 Skill 包

1. 创建 `new-skill/SKILL.md`
2. 定义 YAML 头部（name, description, trigger_keywords）
3. 编写执行流程和输出规范
4. （可选）添加 scripts/ 和 references/

### 5.3 添加新 MCP 工具

1. 在 `server.py` 添加 `@mcp.tool()` 装饰的函数
2. 编写详细 docstring（作为工具描述）
3. 实现参数验证和错误处理

---

## 6. 部署与运行

### 6.1 环境要求

- Python ≥ 3.13
- 依赖：`uv sync` 自动安装
- API Key：配置 `.env` 文件

### 6.2 启动流程

```bash
# 1. 初始化数据库
uv run init_db.py

# 2. 启动 Agent（交互式选择模型）
uv run agent.py
```

### 6.3 数据库初始化

`init_db.py` 创建 52 条 Q2 测试数据：
- 5 个产品 × 3 个区域 × 4-6 月
- 包含正常销售和 618 促销场景

---

## 7. 关键技术决策

### 7.1 为什么选择 MCP 协议？

- **标准化**：统一工具调用接口，与具体 LLM 解耦
- **可扩展**：支持stdio、SSE、WebSocket 等多种传输方式
- **生态**：Anthropic 推动，社区工具丰富

### 7.2 为什么采用渐进式 Skill 加载？

- **Token 成本**：避免一次性加载所有 Skill 的完整指令
- **响应速度**：启动时仅加载摘要（~100 tokens）
- **按需加载**：匹配后才加载完整指令和脚本

### 7.3 为什么设计双层记忆系统？

- **向量记忆**：支持语义检索，跨会话关联相关内容
- **SQLite 记录**：精确回溯，支持工具调用链分析
- **互补**：向量记忆用于"联想"，SQLite 用于"精确还原"

---

## 8. 目录结构

```
.
├── agent.py                    # Agent 入口
├── agent/
│   ├── __init__.py
│   ├── core.py                 # Agent 核心逻辑
│   ├── skill_loader.py         # Skill 加载器
│   ├── backends/
│   │   ├── __init__.py
│   │   ├── base.py             # 后端抽象基类
│   │   ├── qwen.py             # 通义千问后端
│   │   ├── glm.py              # 智谱 GLM 后端
│   │   └── ollama.py           # Ollama 后端
│   └── commands/
│       ├── __init__.py
│       ├── memory.py           # /memory 命令
│       └── history.py          # /history 命令
├── server.py                   # MCP Server
├── memory_store.py             # 向量记忆模块
├── conversation_store.py       # 会话记录模块
├── init_db.py                  # 数据库初始化
├── sales-analysis/             # Skill 包
│   ├── SKILL.md
│   ├── scripts/
│   │   ├── calculate_metrics.py
│   │   └── detect_anomaly.py
│   └── references/
│       └── report_template.md
├── object_db/                  # 数据库存储
│   ├── sales.db
│   ├── memory_db/
│   └── conversations.db
├── pyproject.toml              # 项目配置
├── README.md
└── docs/
    └── ARCHITECTURE.md         # 本文档
```

---

## 9. 附录

### 9.1 斜杠命令列表

| 命令 | 说明 |
|------|------|
| `/new` | 创建新会话 |
| `/memory list` | 列出最近 10 条记忆 |
| `/memory search <关键词>` | 语义搜索记忆 |
| `/memory delete <ID>` | 删除指定记忆 |
| `/memory clear` | 清空所有记忆 |
| `/memory stats` | 查看记忆统计 |
| `/history` | 列出最近会话 |
| `/history show <ID>` | 查看会话详情 |
| `/history resume <ID>` | 恢复历史会话 |
| `/history delete <ID>` | 删除指定会话 |
| `/history clear` | 清空所有会话 |
| `/history stats` | 查看会话统计 |
| `/help` | 显示帮助 |
| `/exit` | 退出程序 |

### 9.2 环境变量

| 变量 | 说明 |
|------|------|
| `DASHSCOPE_API_KEY` | 通义千问 API Key |
| `BIGMODEL_API_KEY` | 智谱 GLM API Key |
| `OLLAMA_BASE_URL` | Ollama 服务地址 |
| `OLLAMA_MODEL` | Ollama 模型名称 |

---

*文档版本: 1.0*  
*最后更新: 2026-04-05*
