# MCP + Skills 销售分析 Agent — 优化与增强建议

> 分析日期：2026-04-05
> 更新日期：2026-04-05（实现）
> 忽略项：测试相关

---

## 一、架构优化

### 1.1 后端架构重构 ⚠️ 优先级：高

**现状**：
- `OpenAICompatibleBackend` 抽象基类处理了 GLM/Ollama 的共性
- 但 `QwenBackend` 独立实现，没有复用 `OpenAICompatibleBackend`
- 各后端的 `check()` 方法分散在多个文件中

**建议**：
```python
# 重构后的架构
agent/backends/
├── base.py              # BaseBackend 抽象基类
├── openai_compat.py     # OpenAICompatibleBackend（GLM/Ollama 共享）
├── qwen.py              # QwenBackend（DashScope 独立 API）
├── provider.py          # ProviderFactory 工厂类，统一创建后端
└── registry.py          # 后端注册表（支持动态注册新后端）
```

**具体改进**：
- [ ] 创建 `ProviderFactory` 工厂类，统一后端创建逻辑
- [ ] 添加后端能力检测（是否支持流式、tools、最大上下文等）
- [ ] 支持后端热切换（无需重启 Agent）
- [ ] 添加后端健康检查定时任务

### 1.2 MCP 连接优化 ✅ 已完成

**实现文件**：`agent/retry.py`

```python
from agent.retry import MCPSessionManager, RetryError

# 带重试的连接
manager = MCPSessionManager()
await manager.connect_with_retry(connect_func)

# 带重试的工具调用
result = await manager.call_tool_with_retry("get_sales_overview", {})
```

**特性**：
- [x] 3次重试（可配置）
- [x] 指数退避（1s → 2s → 4s）
- [x] 随机抖动（避免惊群效应）
- [x] 可配置的最大延迟
- [x] 智能错误检测
                return await self.connect(params)
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(self.retry_delay)
```

**具体改进**：
- [ ] 添加 MCP 连接重试机制（3次重试，指数退避）
- [ ] 添加 MCP Server 健康检查
- [ ] 支持多个 MCP Server 并行连接
- [ ] 连接断开后自动重连

---

## 二、功能增强

### 2.1 缓存层 📊 优先级：中

**现状**：
- 每次查询都直接访问数据库
- 相同的查询没有缓存

**建议**：
```python
# 添加查询缓存
class QueryCache:
    def __init__(self, ttl: int = 300):  # 5分钟 TTL
        self._cache = TTLCache(maxsize=100, ttl=ttl)

    def get(self, tool_name: str, params: dict) -> str | None:
        key = self._make_key(tool_name, params)
        return self._cache.get(key)

    def set(self, tool_name: str, params: dict, result: str):
        key = self._make_key(tool_name, params)
        self._cache[key] = result
```

**具体改进**：
- [ ] 添加工具调用结果缓存（TTL 可配置）
- [ ] 支持缓存失效（数据更新后主动清除）
- [ ] 添加缓存命中率统计
- [ ] 支持按工具类型设置不同 TTL

### 2.2 会话管理增强 📋 优先级：中

**现状**：
- 会话只能通过 ID 查看
- 没有批量操作

**建议**：
```bash
# 新增命令
/history export <session_id>   # 导出会话为 JSON
/history import <file>         # 导入会话
/history search "关键词"        # 搜索历史消息
/history stats --by-model       # 按模型统计
```

**具体改进**：
- [ ] 会话导出/导入（JSON 格式）
- [ ] 会话内搜索功能
- [ ] 按模型、时间范围筛选会话
- [ ] 会话对比功能（两份会话的关键差异）

### 2.3 进化引擎增强 🧬 优先级：中

**现状**：
- 假设确认需要手动处理
- 没有自动学习机制

**建议**：
```python
# 增强的进化引擎
class EvolutionEngineV2:
    # 自动学习模式
    def enable_auto_learn(self, threshold: float = 0.8):
        """置信度超过阈值时自动转为约束"""
        ...

    # 约束冲突检测
    def detect_conflicts(self, new_constraint: str) -> list[str]:
        """检测与现有约束的冲突"""
        ...
```

**具体改进**：
- [ ] 添加自动学习模式（高置信度假设自动确认）
- [ ] 约束冲突检测与提示
- [ ] 画像数据版本管理（支持回滚）
- [ ] 画像导出/导入（跨环境迁移）

### 2.4 Skill 系统扩展 📦 优先级：中

**现状**：
- 只支持单个 skill 包
- 匹配逻辑简单

**建议**：
```python
class SkillManager:
    def load_all_skills(self, skills_dir: Path):
        """扫描并加载多个 skill 包"""

    def match_skills(self, user_input: str) -> list[dict]:
        """返回多个匹配度最高的技能"""
```

**具体改进**：
- [ ] 支持多个 Skill 包目录
- [ ] Skill 包版本管理
- [ ] Skill 优先级配置
- [ ] Skill 组合执行（多个 Skill 协同）
- [ ] Skill 市场支持（从 URL 加载）

---

## 三、性能优化

### 3.1 数据库连接池 ⚡ 优先级：高

**现状**：
- 每个操作都创建新连接
- 没有连接复用

**建议**：
```python
# 使用连接池
from sqlite3 import dbapi2 as sqlite
from sqlitepool import ConnectionPool

class DBPool:
    def __init__(self, db_path: str, pool_size: int = 5):
        self._pool = ConnectionPool(sqlite, db_path, pool_size)
```

**具体改进**：
- [ ] server.py 使用连接池
- [ ] conversation_store.py 使用连接池
- [ ] profile_store.py 使用连接池

### 3.2 异步优化 ⚡ 优先级：中

**现状**：
- `core.py` 中有些地方使用 threading 而不是 asyncio
- 流式输出使用 queue.Queue（同步）

**建议**：
```python
# 改用异步队列
import asyncio

async def process_streaming(self):
    queue = asyncio.Queue()
    # 使用 asyncio.gather 并行处理
```

**具体改进**：
- [ ] 将 threading 改为 asyncio
- [ ] 使用 `asyncio.to_thread` 处理阻塞 I/O
- [ ] 添加请求超时控制

### 3.3 内存优化 ⚡ 优先级：低

**现状**：
- 消息历史无限增长
- 恢复会话时加载所有历史消息

**建议**：
```python
# 滑动窗口 + 摘要压缩
MAX_CONTEXT_LENGTH = 50  # 最大保留消息数
SUMMARY_THRESHOLD = 30   # 超过后触发摘要

class ConversationManager:
    def _maybe_summarize(self, messages: list):
        if len(messages) > SUMMARY_THRESHOLD:
            summary = await self._generate_summary(messages)
            # 压缩为摘要消息
```

**具体改进**：
- [ ] 消息历史滑动窗口
- [ ] 自动摘要压缩（保留关键信息）
- [ ] 大会话分页加载

---

## 四、开发者体验

### 4.1 CLI 增强 🛠️ 优先级：中

**现状**：
- 只有 REPL 和 TUI 两种模式
- 缺少调试工具

**建议**：
```bash
# 新增命令
uv run agent.py --debug                    # 调试模式（详细日志）
uv run agent.py --eval "查询销售额"        # 单次执行模式
uv run agent.py --benchmark                # 性能基准测试
uv run agent.py --export-skills            # 导出 Skill 配置
```

**具体改进**：
- [ ] `--debug` 调试模式
- [ ] `--eval` 单次执行模式
- [ ] `--benchmark` 性能测试
- [ ] `--config` 查看/编辑配置

### 4.2 日志系统增强 📝 优先级：中

**现状**：
- 使用统一的 `agent/log.py`
- 但日志级别不够细分

**建议**：
```python
# 分模块日志级别
logger.setLevel(logging.DEBUG)  # 全局 WARNING
logger.debug("工具调用: %s", tool_name)  # 但工具调用用 DEBUG
```

**具体改进**：
- [ ] 分模块日志级别配置
- [ ] 日志文件输出（支持轮转）
- [ ] 结构化日志（JSON 格式）
- [ ] 敏感信息自动脱敏

### 4.3 配置管理 ⚙️ 优先级：中

**现状**：
- 配置分散在 .env 和代码中
- 没有统一配置管理

**建议**：
```python
# config.yaml
server:
  host: "0.0.0.0"
  port: 8080

agent:
  max_retries: 3
  cache_ttl: 300
  max_context_length: 50

evolution:
  auto_learn: false
  confidence_threshold: 0.8
```

**具体改进**：
- [ ] 统一配置文件（YAML）
- [ ] 环境变量覆盖
- [ ] 配置验证与提示
- [ ] 配置热重载

---

## 五、安全加固

### 5.1 API 密钥管理 🔒 优先级：高

**现状**：
- API 密钥明文存储在 .env
- 没有密钥轮换机制

**建议**：
```python
# 使用 keyring 安全存储
import keyring

class SecretManager:
    def get_api_key(self, service: str) -> str:
        return keyring.get_password("sales-agent", service)

    def set_api_key(self, service: str, key: str):
        keyring.set_password("sales-agent", service, key)
```

**具体改进**：
- [ ] 使用 keyring 存储敏感信息
- [ ] 支持密钥轮换
- [ ] 密钥使用审计日志

### 5.2 输入验证增强 🔒 优先级：中

**现状**：
- SQL 注入已防护
- 但一些边界情况未处理

**建议**：
```python
# 增强验证
class InputValidator:
    MAX_QUERY_LENGTH = 500
    MAX_RESULTS = 1000

    def validate_product_name(self, name: str) -> str:
        if len(name) > self.MAX_QUERY_LENGTH:
            raise ValueError("查询过长")
        # 特殊字符检查
        if re.search(r"[^\w\s\-\u4e00-\u9fff]", name):
            raise ValueError("包含非法字符")
        return name.strip()
```

**具体改进**：
- [ ] 统一输入验证层
- [ ] 查询结果数量限制
- [ ] 速率限制（防止滥用）

---

## 六、可观测性

### 6.1 指标收集 📈 优先级：中

**现状**：
- 没有指标收集
- 无法量化 Agent 表现

**建议**：
```python
# 指标收集
metrics = {
    "tool_calls_total": Counter,
    "tool_call_duration": Histogram,
    "cache_hit_rate": Gauge,
    "user_satisfaction": Gauge,  # 基于反馈
}
```

**具体改进**：
- [ ] 工具调用计数和耗时
- [ ] 缓存命中率
- [ ] 用户满意度（可选反馈）
- [ ] 各后端成功率对比

### 6.2 追踪系统 🔍 优先级：低

**现状**：
- 没有分布式追踪

**建议**：
```python
# 简单的请求追踪
trace_id = generate_trace_id()
with tracer.start_span("tool_call") as span:
    span.set_attribute("tool.name", tool_name)
    result = await call_tool(...)
```

**具体改进**：
- [ ] 请求链路追踪
- [ ] 性能剖析
- [ ] 错误追踪

---

## 七、扩展性

### 7.1 MCP Server 插件化 🔌 优先级：中

**现状**：
- 工具硬编码在 server.py

**建议**：
```python
# 插件目录
plugins/
├── __init__.py
├── sales/              # 内置销售工具
├── marketing/          # 营销工具（可扩展）
└── inventory/          # 库存工具（可扩展）

# 自动发现插件
class PluginManager:
    def discover_plugins(self):
        for dir in Path("plugins").iterdir():
            if dir.is_dir() and (dir / "plugin.py").exists():
                self.load_plugin(dir)
```

**具体改进**：
- [ ] 插件目录自动发现
- [ ] 插件版本管理
- [ ] 插件沙箱隔离

### 7.2 后端代理 🌍 优先级：低

**现状**：
- 只支持直接调用后端

**建议**：
```python
# 添加代理支持
class ProxiedBackend(BaseBackend):
    def __init__(self, target: BaseBackend, proxy_url: str):
        self._target = target
        self._proxy = proxy_url
```

**具体改进**：
- [ ] HTTP 代理支持
- [ ] 负载均衡（多后端）
- [ ] 熔断器模式

---

## 八、优先级矩阵

| 功能 | 复杂度 | 影响 | 优先级 |
|------|--------|------|--------|
| MCP 连接重试机制 | 低 | 高 | 🔴 高 |
| 数据库连接池 | 中 | 高 | 🔴 高 |
| API 密钥安全存储 | 中 | 高 | 🔴 高 |
| 后端工厂重构 | 中 | 中 | 🟡 中 |
| 工具调用缓存 | 低 | 中 | 🟡 中 |
| 会话导出/导入 | 低 | 中 | 🟡 中 |
| 进化引擎增强 | 中 | 中 | 🟡 中 |
| 配置统一管理 | 低 | 中 | 🟡 中 |
| Skill 多包支持 | 高 | 中 | 🟢 低 |
| 插件系统 | 高 | 中 | 🟢 低 |
| 指标收集 | 中 | 低 | 🟢 低 |
| 异步优化 | 中 | 低 | 🟢 低 |

---

## 九、实施建议

### 阶段 1：稳定性优先（1-2 周）
1. 添加 MCP 连接重试
2. 数据库连接池
3. API 密钥安全存储
4. 统一输入验证

### 阶段 2：体验优化（2-3 周）
1. 工具调用缓存
2. 会话管理增强
3. CLI 增强
4. 配置管理

### 阶段 3：高级功能（长期）
1. 进化引擎增强
2. Skill 系统扩展
3. 插件系统
4. 可观测性

---

*报告生成时间：2026-04-05*
