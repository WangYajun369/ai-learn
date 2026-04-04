# MCP + Skills 销售分析 Agent

一个基于 MCP（Model Context Protocol）的 AI Agent 示例项目，演示如何通过 **MCP 工具 + Skills 技能包** 构建一个具备"专家级分析能力"的智能助手。

## 架构

```
用户（自然语言）
    ↓
agent.py（MCP Client + Skill Engine + LLM Backend）
    ↓ stdio
server.py（MCP Server — 销售数据工具集）
    ↓
sales.db（SQLite 销售数据库）
```

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

# 初始化数据库
uv run init_db.py

# 运行 Agent
uv run agent.py
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
