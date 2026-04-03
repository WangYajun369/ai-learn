# MCP + AI Agent 最小示例

基于 [MCP（Model Context Protocol）](https://modelcontextprotocol.io/) 的 AI Agent 示例项目，演示如何让大模型通过工具调用查询本地数据库。

## 项目架构

```
用户终端（自然语言输入）
    ↓
agent.py（MCP Client + LLM 后端）
    ↓ stdio 子进程协议
server.py（MCP Server / 工具提供方）
    ↓
sales.db（SQLite 数据库）
```

## 功能特性

- **双模型支持** — 通义千问 qwen-max / 智谱 GLM-4.5-Air，启动时交互式选择
- **模型可用性检查** — 自动验证 API Key 和网络连通性，不可用时引导重新选择
- **多步工具调用** — 支持链式推理，模型可连续调用多个工具完成复杂任务
- **产品列表查询** — 查询数据库中所有已有的产品名称
- **模糊匹配查询** — 产品名称忽略空格差异（如"AI助手专业版"与"AI 助手专业版"均能匹配）
- **中文输入优化** — 使用 prompt_toolkit 处理终端输入，中文光标移动和删除无错位

## 快速开始

### 1. 安装依赖

```bash
uv sync
```

### 2. 配置 API Key

在项目根目录创建 `.env` 文件（已有则编辑）：

```env
# 通义千问（二选一即可）
DASHSCOPE_API_KEY=你的 DashScope API Key

# 智谱 GLM（二选一即可）
BIGMODEL_API_KEY=你的 BigModel API Key
```

> ⚠️ **安全提醒**：请勿将包含真实 API Key 的 `.env` 文件提交到 Git 仓库。

### 3. 初始化数据库

```bash
uv run init_db.py
```

> 只需运行一次。重复运行不会报错（已存在的数据会自动跳过）。

### 4. 启动 Agent

```bash
uv run agent.py
```

启动后会弹出模型选择菜单，使用 **↑↓ 方向键**移动，**Enter** 确认：

```
🤖 请选择大模型后端（↑↓ 移动，Enter 确认）：

  ❯ 通义千问 qwen-max（DashScope）
    智谱 GLM-4.5-Air（BigModel）
    退出程序
```

选择后自动检查模型可用性，不可用时提示重新选择。

### 5. 开始对话

启动成功后会显示已加载的工具列表，然后进入对话模式：

```
✅ 已加载 2 个工具：
   - query_sales_by_product：查询指定产品的销售记录汇总。
   - list_products：查询数据库中所有已有的产品名称列表。

👤 你：有哪些产品？
🔧 调用工具：list_products({})...
🤖 Agent：📦 **产品列表**
           1. AI 助手专业版
           2. AI 助手企业版
```

```
👤 你：帮我查一下AI助手专业版的销售情况
🔧 调用工具：query_sales_by_product({'product_name': 'AI助手专业版'})...
🤖 Agent：📊 **AI助手专业版 销售简报**
           总销售额：¥27,000.00
           成交笔数：2
           ...
```

输入 `exit` 或 `quit` 退出对话。

## 可用工具

| 工具 | 说明 |
|---|---|
| `query_sales_by_product` | 根据产品名称查询销售记录，支持模糊匹配 |
| `list_products` | 查询数据库中所有已有产品名称 |

## 技术栈

| 组件 | 技术 | 说明 |
|---|---|---|
| 包管理 | [uv](https://docs.astral.sh/uv/) | 快速 Python 包管理器 |
| Python | [3.13+](https://www.python.org/) | 编程语言 |
| MCP Server | [fastmcp](https://gofastmcp.com/) >= 3.2 | MCP 服务端框架 |
| MCP Client | [mcp](https://github.com/modelcontextprotocol/python-sdk) >= 1.27 | MCP 客户端 SDK |
| 大模型 A | [qwen-max](https://www.aliyun.com/product/tongyi?spm=5176.29619931.J_4VYgf18xNlTAyFFbOuOQe.d_menu_0.34d210d781XBpG) | 通义千问 |
| 大模型 B | [GLM-4.5-Air](https://www.bigmodel.cn/invite?icode=fiCghm9emueP%2FIo%2FcVcvYFwpqjqOwPB5EXW6OL4DgqY%3D/) | 智谱 AI |
| 交互选择 | [pick](https://github.com/wong2/pick) >= 2.2 | 终端上下键菜单 |
| 终端输入 | [prompt_toolkit](https://github.com/prompt-toolkit/python-prompt-toolkit) >= 3.0 | 中文输入支持 |
| 数据库 | [SQLite](https://github.com/sqlite/sqlite) | Python 内置 |
| 环境变量 | [python-dotenv](https://github.com/theskumar/python-dotenv) | .env 文件管理 |

## 项目结构

```
issue-1/
├── agent.py        # MCP Client + Agent 核心（双后端策略模式）
├── server.py       # MCP Server（销售数据查询工具）
├── init_db.py      # 数据库初始化脚本
├── sales.db        # SQLite 数据库（销售记录）
├── pyproject.toml  # 项目配置与依赖声明
├── .env            # API Key 配置（不提交到 Git）
└── README.md
```

## 核心设计

### 策略模式（双模型后端）

```python
class QwenBackend:    # DashScope functions / function_call 格式
class GLMBackend:     # OpenAI-style tools / tool_calls 格式
```

两个后端实现统一接口：

| 方法 | 说明 |
|---|---|
| `check()` | 验证 API Key 和连通性 |
| `build_tools(mcp_tools)` | 将 MCP 工具转换为模型对应格式 |
| `chat(messages, tools)` | 调用模型，返回统一结构 `{content, tool_calls, raw_message}` |
| `make_tool_result_message(tool_call, text)` | 构造工具结果消息（格式因模型而异） |

### 多步工具调用循环

```
用户输入 → 调用模型 → 有工具调用？
                       ├─ 是 → 执行工具 → 将结果喂回模型 → 继续判断
                       └─ 否 → 输出最终回复
```

### 中文输入处理

使用 `prompt_toolkit.PromptSession` 替代 Python 内置 `input()`，解决以下问题：
- 中文字符光标定位错位
- 退格删除异常
- 左右方向键移动跳字

在异步上下文中使用 `prompt_async()` 方法，避免与 `asyncio` 事件循环冲突。

## 添加新模型

只需实现四个方法即可接入新的模型后端：

```python
class NewBackend:
    def check(self) -> str | None: ...
    def build_tools(self, mcp_tools) -> list: ...
    def chat(self, messages, tools) -> dict: ...
    def make_tool_result_message(self, tool_call, result_text) -> dict: ...

# 注册
BACKENDS["new"] = NewBackend
BACKEND_LABELS["new"] = "新模型名称（提供商）"
```
