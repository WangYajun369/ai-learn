# 7层记忆架构设计方案

> 基于4层记忆系统（向量记忆、会话记录、进化式记忆、工具缓存）扩展，构建更完整的AI Agent记忆体系。

---

## 1. 架构概览

### 1.1 记忆层次结构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        7层记忆金字塔                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  L7 知识库记忆    ▲          │
│  (Knowledge Base)   │ 长期积累   │
│  ──────────────────┼───────────  │
│                     │            │
│  L6 反思记忆        ▲ 知识沉淀   │
│  (Reflection)       │            │
│  ──────────────────┼───────────  │
│                     │            │
│  L5 进化式记忆      ▲ 能力提升   │
│  (Evolution)        │            │
│  ──────────────────┼───────────  │
│                     │            │
│  L4 会话记录        ▲ 经验回溯   │
│  (Conversation)     │            │
│  ──────────────────┼───────────  │
│                     │            │
│  L3 向量记忆        ▲ 关联检索   │
│  (Vector)           │            │
│  ──────────────────┼───────────  │
│                     │            │
│  L2 工具缓存        ▲ 性能优化   │
│  (Tool Cache)       │            │
│  ──────────────────┼───────────  │
│                     │            │
│  L1 短期工作记忆    ▲ 临时存储   │
│  (Working Memory)    │            │
│  └─────────────────┴───────────  │
│                     │            │
│                     ↓            │
│              当前对话上下文      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 7层记忆职责矩阵

| 层级 | 记忆类型 | 存储介质 | 生命周期 | 检索策略 | 主要用途 |
|------|----------|----------|----------|----------|----------|
| **L1** | 短期工作记忆 | 内存结构 | 单次会话 | O(1)直接访问 | 当前上下文临时存储 |
| **L2** | 工具缓存 | 内存（LRU） | TTL过期（默认300s） | 哈希匹配 | 相同查询秒级响应 |
| **L3** | 向量记忆 | ChromaDB | 长期持久 | 语义相似度 | 跨会话关联检索 |
| **L4** | 会话记录 | SQLite | 长期持久 | 精确匹配 | 完整历史回溯 |
| **L5** | 进化式记忆 | SQLite | 长期持久 | 分类检索 | 用户画像学习 |
| **L6** | 反思记忆 | SQLite | 长期持久 | 情境匹配 | Agent自我改进 |
| **L7** | 知识库记忆 | SQLite | 长期持久 | 语义/关键词 | 结构化知识管理 |

---

## 2. 各层记忆详解

### 2.1 L1 短期工作记忆（新增）

#### 职责
- 存储当前会话的临时上下文信息
- 维护对话状态（变量、中间结果）
- 管理会话内的临时引用

#### 数据结构
```python
@dataclass
class WorkingMemory:
    """短期工作记忆"""
    session_id: str
    turn_count: int
    variables: dict[str, Any]  # 会话内变量
    references: dict[str, str]  # 临时引用：{变量名: 引用说明}
    context_tags: list[str]  # 当前上下文标签
    last_update: float  # 最后更新时间戳
```

#### 示例场景
```python
# 用户: "分析华东区的销售"
# WorkingMemory 记录：
{
    "variables": {"region": "华东", "intent": "sales_analysis"},
    "references": {
        "华东": "用户分析目标区域",
        "销售额": "关注的核心指标"
    },
    "context_tags": ["销售分析", "区域查询", "华东"]
}

# 用户追问: "和华南比怎么样？"
# 从 WorkingMemory 快速获取之前的 "region" 进行对比
```

#### 特性
- 会话结束时自动清理
- 支持 `/context` 命令查看当前工作记忆
- 变量可跨轮引用：`$region` → 华东

---

### 2.2 L2 工具缓存（现有）

#### 职责
- 缓存工具调用结果
- 相同参数查询直接返回
- 降低API调用成本和延迟

#### 配置
```yaml
cache:
  enabled: true
  ttl_seconds: 300
  max_size: 1000
```

---

### 2.3 L3 向量记忆（现有）

#### 职责
- 存储对话摘要
- 语义检索相关历史
- 跨会话知识关联

#### 数据结构
```python
{
    "id": "mem_xxx",
    "content": "用户关注华东区销售，偏好数据可视化...",
    "embedding": [...],  # 1536维向量
    "metadata": {
        "session_id": "20260405_100100",
        "timestamp": "2024-04-05T10:01:00",
        "topics": ["华东", "销售", "数据可视化"],
        "confidence": 0.8
    }
}
```

---

### 2.4 L4 会话记录（现有）

#### 职责
- 完整会话历史存储
- 工具调用链追踪
- 会话搜索和导出

#### 表结构
```sql
sessions:      id, model, started_at, ended_at, turn_count, status, title, tags
messages:      id, session_id, role, content, turn_order, created_at
tool_calls:    id, session_id, message_id, tool_name, arguments, result, duration_ms, created_at
```

---

### 2.5 L5 进化式记忆（现有）

#### 职责
- 用户画像学习（偏好/约束/工作流）
- 假设队列管理
- Agent自我进化

#### 数据结构
```sql
-- 用户画像表
user_profiles:
  id, category, content, source, confidence, occurrence_count, created_at, updated_at

-- 假设队列表
hypotheses:
  id, hypothesis, context, trigger_keywords, prompt_count, status, created_at, updated_at
```

---

### 2.6 L6 反思记忆（新增）

#### 职责
- 记录Agent的自我反思
- 追踪错误和改进点
- 积累最佳实践

#### 数据结构
```python
@dataclass
class Reflection:
    """反思记录"""
    id: str
    session_id: str
    turn_order: int
    reflection_type: str  # error|success|insight|improvement
    trigger: str  # 触发反思的场景描述
    content: str  # 反思内容
    action_taken: str  # 采取的改进措施
    effectiveness: float  # 改进效果评分 0-1
    created_at: datetime
```

#### 表结构
```sql
CREATE TABLE reflections (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    turn_order INTEGER NOT NULL,
    reflection_type TEXT NOT NULL,  -- error|success|insight|improvement
    trigger TEXT NOT NULL,
    content TEXT NOT NULL,
    action_taken TEXT,
    effectiveness REAL DEFAULT 0.0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (session_id) REFERENCES sessions(id)
);

CREATE INDEX idx_reflection_type ON reflections(reflection_type);
CREATE INDEX idx_reflection_effectiveness ON reflections(effectiveness DESC);
```

#### 反思触发场景
| 类型 | 触发条件 | 示例 |
|------|----------|------|
| **error** | 工具调用失败/超时 | "MCP连接超时，需要增加重试次数" |
| **success** | 高价值响应被用户认可 | "用户说'很有用'，记录此分析模式" |
| **insight** | 发现新的用户行为模式 | "用户每次都先问产品列表，先自动展示" |
| **improvement** | 响应质量可提升 | "报告太长，下次精简到关键指标" |

#### 反思记忆检索策略
```python
# 检索同类场景的历史反思
similar_reflections = db.query("""
    SELECT * FROM reflections
    WHERE reflection_type = ?
    AND trigger LIKE ?
    ORDER BY effectiveness DESC
    LIMIT 3
""", (reflection_type, f"%{current_trigger}%"))

# 注入到system prompt
if similar_reflections:
    context += "\n\n## 历史反思参考\n"
    for r in similar_reflections:
        context += f"- {r.trigger}: {r.action_taken} (效果: {r.effectiveness})\n"
```

---

### 2.7 L7 知识库记忆（新增）

#### 职责
- 存储结构化领域知识
- 管理业务规则和FAQ
- 支持知识增删改查

#### 数据结构
```python
@dataclass
class Knowledge:
    """知识条目"""
    id: str
    category: str  # domain|rule|faq|pattern|best_practice
    topic: str  # 知识主题
    title: str  # 知识标题
    content: str  # 知识内容
    tags: list[str]  # 标签
    source: str  # 知识来源
    confidence: float  # 可信度 0-1
    usage_count: int  # 使用次数
    last_used_at: datetime  # 最后使用时间
    created_at: datetime
```

#### 表结构
```sql
CREATE TABLE knowledge_base (
    id TEXT PRIMARY KEY,
    category TEXT NOT NULL,  -- domain|rule|faq|pattern|best_practice
    topic TEXT NOT NULL,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    tags TEXT,  -- JSON array
    source TEXT,
    confidence REAL DEFAULT 1.0,
    usage_count INTEGER DEFAULT 0,
    last_used_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_knowledge_category ON knowledge_base(category);
CREATE INDEX idx_knowledge_tags ON knowledge_base(tags);
CREATE INDEX idx_knowledge_usage ON knowledge_base(usage_count DESC);
```

#### 知识分类
| 类别 | 说明 | 示例 |
|------|------|------|
| **domain** | 领域知识 | "618促销期销售额通常增长30-50%" |
| **rule** | 业务规则 | "Q2数据统计范围：4-6月" |
| **faq** | 常见问题 | "如何切换模型？" |
| **pattern** | 用户行为模式 | "用户常用'对比XX和XX'句式" |
| **best_practice** | 最佳实践 | "销售报告应包含总销售额、增长率、异常点" |

#### 知识管理命令
```bash
/knowledge add           # 添加知识
/knowledge search <关键词>  # 搜索知识
/knowledge list           # 列出所有知识
/knowledge get <ID>       # 查看知识详情
/knowledge update <ID>     # 更新知识
/knowledge delete <ID>     # 删除知识
/knowledge import <文件>    # 批量导入知识
/knowledge export          # 导出知识库
```

---

## 3. 记忆检索与注入流程

### 3.1 统一注入器架构

```
用户输入
    ↓
┌─────────────────────────────────────────────────────────────────┐
│                    MemoryInjector (统一注入器)                  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  L1 WorkingMemory    → 当前会话变量、上下文标签                │
│  L2 ToolCache        → 检查缓存命中                           │
│  L3 VectorMemory     → 语义检索相关摘要（n=3）                   │
│  L4 Conversation     → （被动，通过/history命令访问）              │
│  L5 Evolution        → 用户画像 + 待确认假设                     │
│  L6 Reflection       → 同类场景的历史反思（n=2）                  │
│  L7 Knowledge        → 匹配的知识条目（n=3）                    │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
    ↓
system_prompt = base_system_prompt + 所有检索到的记忆内容
    ↓
发送给LLM
```

### 3.2 注入优先级与格式

```python
def build_enhanced_system_prompt(user_input: str, base_prompt: str) -> str:
    """构建增强版system prompt"""

    sections = [base_prompt]

    # L1: 工作记忆（最高优先级）
    if wm := working_memory.get_context():
        sections.append(f"## 当前对话上下文\n{wm}")

    # L7: 知识库（领域知识）
    if kb := knowledge.search(user_input, n=3):
        sections.append(f"## 相关知识\n{format_knowledge(kb)}")

    # L6: 反思记忆（避免重复错误）
    if reflections := reflection.get_similar(user_input, n=2):
        sections.append(f"## 历史反思\n{format_reflections(reflections)}")

    # L3: 向量记忆（会话摘要）
    if vector_mem := memory_store.search(user_input, n=3):
        sections.append(f"## 历史对话摘要\n{format_vector_mem(vector_mem)}")

    # L5: 进化记忆（用户画像）
    if profile := evolution.get_profile_for_prompt():
        sections.append(f"## 用户画像\n{profile}")

    # L5: 假设提示
    if hint := evolution.get_hypothesis_hint(user_input):
        sections.append(f"## 待确认提示\n{hint}")

    return "\n\n".join(sections)
```

---

## 4. 记忆协同工作流程

### 4.1 对话前准备
```
1. L1 WorkingMemory 初始化/恢复
2. L2 ToolCache 检查（如有相同查询）
3. L3-L7 联合检索 → 注入 system prompt
4. L5 检查待确认假设 → 准备提示
```

### 4.2 对话中处理
```
1. L1 WorkingMemory 记录本轮变量和标签
2. L2 ToolCache 检查/更新缓存
3. L4 Conversation 实时记录消息和工具调用
```

### 4.3 对话后处理
```
1. L1 WorkingMemory 保持（下一轮继续使用）
2. L3 VectorMemory 生成并存储摘要
3. L4 Conversation 标记会话状态
4. L5 Evolution 观察并更新画像/假设
5. L6 Reflection 触发反思（如满足条件）
6. L7 Knowledge 更新使用统计
```

### 4.4 会话结束
```
1. L1 WorkingMemory 清空
2. L4 Conversation 关闭会话
3. L3 VectorMemory 存储最终摘要
4. L5 Evolution 执行深度分析（如需要）
5. L6 Reflection 总结会话级反思
```

---

## 5. 记忆一致性保证

### 5.1 数据一致性
```python
class MemoryConsistencyChecker:
    """记忆一致性检查器"""

    def check_cross_layer_conflicts(self) -> list[dict]:
        """检查跨层记忆冲突"""
        conflicts = []

        # 检查L5用户画像与L7知识库的冲突
        profile_constraints = evolution.get_by_category("constraint")
        kb_rules = knowledge.get_by_category("rule")

        for constraint in profile_constraints:
            for rule in kb_rules:
                if self._is_conflicting(constraint["content"], rule["content"]):
                    conflicts.append({
                        "type": "profile_vs_knowledge",
                        "profile_id": constraint["id"],
                        "knowledge_id": rule["id"],
                        "description": f"用户约束与知识规则可能冲突：{constraint['content']} vs {rule['content']}"
                    })

        return conflicts

    def _is_conflicting(self, text1: str, text2: str) -> bool:
        """判断两段文本是否冲突（简单实现）"""
        # 可使用LLM进行语义冲突检测
        return False
```

### 5.2 版本控制
```sql
-- 知识库版本表
CREATE TABLE knowledge_versions (
    id TEXT PRIMARY KEY,
    knowledge_id TEXT NOT NULL,
    version INTEGER NOT NULL,
    content TEXT NOT NULL,
    change_reason TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (knowledge_id) REFERENCES knowledge_base(id)
);
```

---

## 6. 增强实施计划

### Phase 1: L1 短期工作记忆（1周）

#### 任务清单
- [ ] 设计 `WorkingMemory` 数据结构
- [ ] 实现 `WorkingMemoryStore` 类
- [ ] 添加 `/context` 命令支持
- [ ] 变量引用机制（`$变量名`）
- [ ] 集成到 `AgentCore.initialize()`

#### 文件变更
```
新增:
  agent/memory/
    ├── __init__.py
    ├── working_memory.py    # L1 实现
    └── consistency_checker.py  # 一致性检查

修改:
  agent/core.py             # 集成 WorkingMemory
  agent/command_dispatcher.py  # 添加 /context 命令
```

#### 验收标准
- [ ] 会话内变量可跨轮引用
- [ ] `/context` 命令正确显示当前工作记忆
- [ ] 会话结束后工作记忆正确清理

---

### Phase 2: L6 反思记忆（2周）

#### 任务清单
- [ ] 设计反思数据结构和表结构
- [ ] 实现 `ReflectionStore` 类
- [ ] 实现反思触发器（`ReflectionTrigger`）
- [ ] LLM反思提示词设计
- [ ] 反思记忆检索和注入
- [ ] 添加 `/reflection` 命令支持

#### 文件变更
```
新增:
  agent/memory/
    ├── reflection.py         # L6 实现
    ├── reflection_trigger.py # 反思触发逻辑

修改:
  agent/core.py              # 集成反思流程
  agent/command_dispatcher.py # 添加 /reflection 命令
```

#### 验收标准
- [ ] 错误场景自动触发反思记录
- [ ] 成功场景可标记最佳实践
- [ ] 同类场景的历史反思正确注入

---

### Phase 3: L7 知识库记忆（2周）

#### 任务清单
- [ ] 设计知识库数据结构和表结构
- [ ] 实现 `KnowledgeStore` 类
- [ ] 知识管理命令实现
- [ ] 知识导入/导出功能
- [ ] 知识检索和注入
- [ ] 初始知识库填充（销售领域）

#### 文件变更
```
新增:
  agent/memory/
    ├── knowledge.py          # L7 实现
    └── knowledge_manager.py # 知识管理命令

修改:
  agent/core.py              # 集成知识检索
  agent/command_dispatcher.py # 添加 /knowledge 命令族
```

#### 验收标准
- [ ] 知识增删改查功能正常
- [ ] 知识导入/导出支持JSON格式
- [ ] 匹配的知识正确注入到system prompt

---

### Phase 4: 统一注入器重构（1周）

#### 任务清单
- [ ] 重构 `MemoryInjector` 支持7层记忆
- [ ] 实现注入优先级管理
- [ ] 优化检索性能（并行检索）
- [ ] 添加调试模式（显示各层检索结果）

#### 文件变更
```
修改:
  agent/memory_injector.py  # 完全重构
  agent/core.py             # 更新注入调用
```

#### 验收标准
- [ ] 7层记忆正确注入到system prompt
- [ ] 注入内容格式清晰易读
- [ ] 调试模式显示各层检索结果

---

### Phase 5: 记忆一致性保证（1周）

#### 任务清单
- [ ] 实现 `MemoryConsistencyChecker`
- [ ] 跨层冲突检测机制
- [ ] 冲突解决策略（提示/自动/忽略）
- [ ] 知识库版本控制

#### 文件变更
```
新增:
  agent/memory/
    └── consistency_checker.py  # 一致性检查

修改:
  agent/command_dispatcher.py # 添加 /check-consistency 命令
```

#### 验收标准
- [ ] 可检测并报告跨层冲突
- [ ] 提供冲突解决建议
- [ ] 知识库版本记录完整

---

### Phase 6: 文档与测试（1周）

#### 任务清单
- [ ] 更新架构文档
- [ ] 编写单元测试
- [ ] 编写集成测试
- [ ] 性能测试和优化

#### 文件变更
```
修改:
  docs/ARCHITECTURE.md     # 更新为7层架构
  docs/7-layer-memory-architecture.md  # 本文档
  tests/                  # 新增测试文件
```

#### 验收标准
- [ ] 测试覆盖率 > 80%
- [ ] 文档完整准确
- [ ] 性能满足要求（检索 < 100ms）

---

## 7. 目录结构（扩展后）

```
.
├── agent/
│   ├── memory/                 # 记忆系统统一目录（新增）
│   │   ├── __init__.py
│   │   ├── working_memory.py   # L1 短期工作记忆
│   │   ├── tool_cache.py      # L2 工具缓存（从cache.py迁移）
│   │   ├── vector_memory.py   # L3 向量记忆（从memory_store.py迁移）
│   │   ├── conversation.py     # L4 会话记录（从conversation_store.py迁移）
│   │   ├── evolution.py       # L5 进化式记忆（从evolution/整合）
│   │   ├── reflection.py      # L6 反思记忆（新增）
│   │   ├── knowledge.py       # L7 知识库记忆（新增）
│   │   └── consistency_checker.py  # 一致性检查（新增）
│   ├── core.py                # Agent 核心
│   └── ...
├── object_db/
│   ├── sales.db
│   ├── memory_db/
│   ├── conversations.db
│   ├── user_profile.db
│   ├── reflections.db           # L6 存储（新增）
│   └── knowledge.db           # L7 存储（新增）
└── docs/
    ├── ARCHITECTURE.md
    └── 7-layer-memory-architecture.md  # 本文档
```

---

## 8. 关键设计决策

### 8.1 为什么增加L1短期工作记忆？
- **问题**：当前会话内的临时状态无法高效传递
- **解决**：提供变量引用机制，支持 `region=$华东` 语法

### 8.2 为什么增加L6反思记忆？
- **问题**：Agent无法从错误中学习，重复犯同样错误
- **解决**：记录反思，同类场景时避免重复错误

### 8.3 为什么增加L7知识库记忆？
- **问题**：领域知识散落在各处，难以统一管理
- **解决**：集中管理结构化知识，支持增删改查

### 8.4 为什么保持各层独立？
- **灵活性**：各层可独立演进
- **可测试性**：单层测试更容易
- **可替换性**：未来可替换某层的实现

---

## 9. 性能考虑

### 9.1 检索性能优化

| 层级 | 检索方式 | 预期耗时 | 优化措施 |
|------|----------|----------|----------|
| L1 | 内存直接访问 | < 1ms | 无需优化 |
| L2 | 哈希匹配 | < 1ms | 无需优化 |
| L3 | 向量检索 | 10-50ms | ChromaDB索引 |
| L4 | SQLite查询 | 5-20ms | WAL模式 + 索引 |
| L5 | SQLite查询 | 5-20ms | 分类索引 |
| L6 | SQLite查询 | 5-20ms | 场景相似度索引 |
| L7 | SQLite+向量 | 20-100ms | 混合检索 |

**并行检索**：L3-L7 可并行检索，总耗时 ≈ max(各层耗时)

### 9.2 存储容量估算

| 层级 | 单条记录大小 | 预估条数 | 总容量 |
|------|-------------|---------|--------|
| L1 | ~1KB | 1 | 1KB |
| L2 | ~2KB | 1000 | 2MB |
| L3 | ~5KB | 10000 | 50MB |
| L4 | ~3KB | 10000 | 30MB |
| L5 | ~1KB | 500 | 500KB |
| L6 | ~2KB | 2000 | 4MB |
| L7 | ~3KB | 1000 | 3MB |
| **总计** | - | - | **~90MB** |

---

## 10. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| 记忆注入过多导致上下文溢出 | 高 | 限制各层注入条目数，优先级排序 |
| 跨层冲突导致行为不一致 | 中 | 一致性检查器 + 冲突解决策略 |
| 性能下降 | 中 | 并行检索 + 缓存优化 |
| 记忆污染（错误信息持久化） | 高 | 置信度机制 + 使用统计 + 用户反馈 |

---

## 11. 总结

### 11.1 核心价值
1. **L1工作记忆**：支持会话内上下文传递和变量引用
2. **L6反思记忆**：Agent从错误中学习，持续改进
3. **L7知识库记忆**：集中管理领域知识，知识可维护

### 11.2 实施路径
- **总周期**：8周
- **优先级**：L7 > L6 > L1（按业务价值）
- **里程碑**：每Phase结束进行验收测试

### 11.3 预期收益
- **响应质量提升**：结构化知识 + 历史反思
- **一致性提升**：跨层冲突检测
- **可维护性提升**：知识库统一管理
- **学习能力提升**：反思机制 + 画像进化

---

*文档版本: 1.0*  
*创建时间: 2026-04-08*  
*作者: Claude*
