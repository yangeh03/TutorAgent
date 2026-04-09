# DeepTutor Memory Architecture

## 四层语义边界

```
┌──────────────────────────────────────────────────────────────┐
│  L0  Working Memory        单次任务执行的暂存区               │
│      (Scratchpad, tool traces, 推理中间态)                    │
│      存储：Python 运行时对象，不持久化                         │
├──────────────────────────────────────────────────────────────┤
│  L1  Session Memory        会话级别的事实源                    │
│      (messages, turns, turn_events, compressed_summary)       │
│      存储：SQLite  data/user/chat_history.db                  │
│      上下文裁剪：ContextBuilder 按 token budget 保留近期消息   │
│                  旧消息压缩成 compressed_summary               │
├──────────────────────────────────────────────────────────────┤
│  L2  Shared Long-term Memory  跨会话的共享用户长期记忆  ★改造层 │
│      底层引擎：mem0 (本地 ChromaDB 向量存储)                   │
│      治理视图：data/memory/PROFILE.md + SUMMARY.md            │
│      详见下方 L2 章节                                         │
├──────────────────────────────────────────────────────────────┤
│  L3  Bot-native Memory     TutorBot 本地记忆                  │
│      (SOUL.md, USER.md, workspace/memory/)                    │
│      每个 Bot 独立维护，不并入共享用户记忆                      │
│      可读取 L2 的 PROFILE.md / SUMMARY.md（只读）             │
└──────────────────────────────────────────────────────────────┘
```

---

## L2 Shared Long-term Memory（mem0 增强）

### 定位

L2 只负责**跨会话、跨 Capability 的共享用户长期记忆**。它不替代 Session 存储，不接管 Bot 本地人格，不存储 scratchpad / tool trace / 推理中间态。

### 记忆分类（MemoryCategory）

| 类别 | 说明 | 归属文件 |
|------|------|----------|
| `identity` | 姓名、角色、背景 | PROFILE.md |
| `preference` | 学习风格、回答格式偏好 | PROFILE.md |
| `knowledge_level` | 各主题掌握程度 | PROFILE.md |
| `learning_goal` | 学习目标 | PROFILE.md |
| `current_topic` | 当前正在学习的主题 | SUMMARY.md |
| `open_question` | 未解决的疑问 | SUMMARY.md |
| `completed_node` | 已完成的学习节点 | SUMMARY.md |
| `recurring_mistake` | 反复出现的错误模式 | SUMMARY.md |

### 模块职责

```
deeptutor/services/memory/
├── contracts.py        数据契约：MemoryCategory, MemoryRecord, IngestionResult
├── provider.py         抽象基类 BaseLongTermMemoryProvider + NullProvider 降级
├── mem0_provider.py    mem0 OSS 实现（本地 ChromaDB）
├── ingestion.py        写路径守门员：过滤 + 抽取 → mem0
├── projection.py       读路径聚合：mem0 → Markdown 视图 / Capability 上下文
└── service.py          统一入口 MemoryService（含 Legacy LLM 重写降级路径）
```

### 写路径（Turn End → mem0）

```
Turn 结束
  ↓
MemoryService.refresh_from_turn()
  ↓
SharedMemoryIngestion.ingest_turn()
  ├── 前置过滤：跳过 < 15 字符的消息、低信号 Capability
  ├── 格式化为 [{"role":"user",...}, {"role":"assistant",...}]
  └── provider.add_from_conversation(messages, infer=True)
        ↓
      mem0 LLM 抽取（使用 custom_fact_extraction_prompt）
        ├── 只抽取：稳定偏好、学习目标、知识水平、当前主题、
        │          待解决问题、已完成节点、反复错误
        ├── 不抽取：寒暄、一次性问题、工具调用细节、临时状态
        └── 自动去重 & 更新已有记忆
  ↓
如果有变更 → _refresh_files_from_projection()
  ├── projection.project_profile() → 写 PROFILE.md
  └── projection.project_summary() → 写 SUMMARY.md
```

**不写入 mem0 的内容：**
- 一次性问题及其答案
- 工具调用 trace、scratchpad
- 寒暄 / 无价值闲聊
- 临时状态（如"我先去吃饭"）

### 读路径（mem0 → LLM 上下文）

```
Turn 开始
  ↓
MemoryService.build_memory_context(capability=..., query=...)
  ↓
SharedMemoryProjection.project_capability_context()
  ├── 根据 Capability 选择不同的记忆分类子集
  └── 格式化为 "## Background Memory" 字符串
  ↓
注入 UnifiedContext.memory_context（与之前完全兼容）
```

**各 Capability 的记忆消费策略：**

| Capability | 消费的记忆分类 | 策略 |
|---|---|---|
| `chat` | identity, preference, current_topic, learning_goal | 全量读取 |
| `guide` / `deep_question` | learning_goal, completed_node, recurring_mistake, open_question, knowledge_level | 聚焦学习进展 |
| `deep_solve` | preference, knowledge_level | 最小化：仅 search(query) 返回相关事实 |
| TutorBot | 读 PROFILE.md / SUMMARY.md 文件 | 与本地 soul/workspace 隔离 |

### PROFILE.md / SUMMARY.md 的角色

- **定位**：可编辑的**治理视图**，不再是唯一数据源
- **自动生成**：每次 mem0 有变更后，由 projection 模块从 mem0 记录聚合重写
- **手工编辑**：用户通过 API (`PUT /api/v1/memory`) 的编辑会**反向同步到 mem0**
- **优先级**：手工编辑 > 自动抽取

### 手工编辑同步

1. 用户通过前端编辑 PROFILE.md 或 SUMMARY.md
2. API 先写入 Markdown 文件
3. `sync_file_to_provider()` 将文件解析为条目
4. 删除 mem0 中对应分类的旧记录
5. 逐条写入新记录，标记 `source=manual`

### 降级策略

当 mem0 不可用（`MEM0_ENABLED=false` 或依赖缺失）时，系统自动降级到原有的 LLM 重写模式：

- 写路径：每轮 turn 结束后用 LLM 重写整个 PROFILE.md / SUMMARY.md
- 读路径：直接读取 Markdown 文件，拼接为 memory_context 字符串
- 与改造前行为完全一致

---

## 存储布局

```
data/
├── user/
│   ├── chat_history.db           ← L1 Session Memory (SQLite)
│   ├── workspace/                ← L3 Bot-native Memory
│   ├── settings/
│   └── logs/
├── memory/                       ← L2 治理视图（Markdown 文件）
│   ├── PROFILE.md
│   └── SUMMARY.md
└── mem0/                         ← L2 向量存储（mem0 本地）
    ├── chroma/                   ← ChromaDB 持久化目录
    └── history.db                ← mem0 操作历史
```

---

## 配置

在 `.env` 中添加：

```env
# --- Long-term Memory (mem0 L2 backend, optional) ---
MEM0_ENABLED=true
MEM0_LLM_PROVIDER=openai        # mem0 用于记忆抽取的 LLM
MEM0_LLM_MODEL=gpt-4o-mini
MEM0_LLM_API_KEY=sk-xxx
MEM0_LLM_BASE_URL=
MEM0_EMBEDDER_PROVIDER=openai   # mem0 用于向量化的 Embedding
MEM0_EMBEDDER_MODEL=text-embedding-3-small
MEM0_EMBEDDER_API_KEY=sk-xxx
MEM0_EMBEDDER_BASE_URL=
```

mem0 的 LLM 和 Embedding **独立于**主系统配置，可以使用更小、更便宜的模型。

---

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/v1/memory` | 读取 PROFILE + SUMMARY 快照 |
| PUT | `/api/v1/memory` | 手工编辑（自动同步回 mem0） |
| POST | `/api/v1/memory/refresh` | 从 Session 重新生成 |
| POST | `/api/v1/memory/clear` | 清空文件 + mem0 |
| GET | `/api/v1/memory/search?q=...` | 语义搜索 mem0 记录 |
