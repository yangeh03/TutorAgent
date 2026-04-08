当前这个系统里，“记忆”其实分成两层来看更清楚：

1. 短期会话记忆：当前会话的历史消息、压缩摘要。
2. 长期共享记忆：跨会话持久化的 `PROFILE.md` 和 `SUMMARY.md`。

如果一句话概括：它不是“向量数据库式长期记忆”，而是“SQLite 会话历史 + LLM 重写出来的 Markdown 长期记忆”。

**1. 记忆是怎么构建的**
主对话链路里，每次 turn 开始时会先构建会话上下文，再读取长期记忆；turn 结束后，再用本轮的 user/assistant 内容去刷新长期记忆。入口在 [turn_runtime.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/services/session/turn_runtime.py#L381) 到 [turn_runtime.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/services/session/turn_runtime.py#L390)，以及 [turn_runtime.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/services/session/turn_runtime.py#L528) 到 [turn_runtime.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/services/session/turn_runtime.py#L535)。

长期记忆服务在 [service.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/services/memory/service.py#L49) 里，核心是两个文件：
- `PROFILE.md`：稳定信息，比如身份、偏好、知识水平。
- `SUMMARY.md`：学习旅程，比如当前在学什么、完成了什么、还有什么问题。见 [service.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/services/memory/service.py#L1) 到 [service.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/services/memory/service.py#L8)。

它不是把一轮对话“追加”进去，而是把“当前记忆 + 新材料”交给 LLM，要求重写整个文档；如果无需修改，就返回 `NO_CHANGE`。这个逻辑在 [service.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/services/memory/service.py#L186) 到 [service.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/services/memory/service.py#L215) 和 [service.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/services/memory/service.py#L272) 到 [service.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/services/memory/service.py#L347)。  
也就是说，它的构建策略是“LLM 重写式归纳”，不是规则抽取，也不是 embedding 聚类。

**2. 记忆存在哪里**
长期共享记忆存到 `data/memory/`，路径由 [path_service.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/services/path_service.py#L210) 决定；历史上旧的 `workspace/memory` 会在读取时迁移过去。  
当前统一聊天会话历史则存在 SQLite，表结构在 [sqlite_store.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/services/session/sqlite_store.py#L83) 到 [sqlite_store.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/services/session/sqlite_store.py#L148)，主要是：
- `sessions`：会话元数据、压缩摘要 `compressed_summary`
- `messages`：逐条消息
- `turns` / `turn_events`：每轮执行和流式事件

消息写入在 [sqlite_store.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/services/session/sqlite_store.py#L494) 到 [sqlite_store.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/services/session/sqlite_store.py#L561)，上下文读取在 [sqlite_store.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/services/session/sqlite_store.py#L591) 到 [sqlite_store.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/services/session/sqlite_store.py#L609)。

**3. 记忆怎么检索和注入模型**
短期检索不是语义检索，而是“按 token budget 裁剪 + 对旧消息做摘要”。逻辑在 [context_builder.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/services/session/context_builder.py#L87) 开始。它会：
- 根据模型 `max_tokens` 分配 history budget，见 [context_builder.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/services/session/context_builder.py#L100) 到 [context_builder.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/services/session/context_builder.py#L108)
- 保留最近消息
- 把更早的消息压缩成 `compressed_summary`
- 写回 `sessions.compressed_summary`，见 [context_builder.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/services/session/context_builder.py#L341) 到 [context_builder.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/services/session/context_builder.py#L377)

长期记忆检索则更简单：直接读取 `PROFILE.md` 和 `SUMMARY.md`，拼成一个 `memory_context` 字符串，最多 4000 字符，见 [service.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/services/memory/service.py#L156) 到 [service.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/services/memory/service.py#L178)。

在 `chat` 能力里，这份长期记忆会作为额外的 system message 注入，见 [agentic_pipeline.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/agents/chat/agentic_pipeline.py#L854) 到 [agentic_pipeline.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/agents/chat/agentic_pipeline.py#L862)。  
所以主 chat 的检索本质上是：
- 先拿短期会话摘要/历史
- 再拿长期 Markdown 记忆
- 一起喂给模型

**4. API 和人工干预**
这个记忆系统有独立 API，可读、可写、可刷新、可清空，见 [memory.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/api/routers/memory.py#L41) 到 [memory.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/api/routers/memory.py#L82)。  
也就是说，除了自动更新，还支持：
- `GET /api/v1/memory`：读取当前记忆
- `PUT /api/v1/memory`：直接改某个文件
- `POST /api/v1/memory/refresh`：从某个 session 重新生成
- `POST /api/v1/memory/clear`：清空

**5. TutorBot 还有一套“归档式记忆”**
如果你说的是 TutorBot 子系统，它还有另一套更 agent-native 的记忆机制。核心在 [memory.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/tutorbot/agent/memory.py#L75) 到 [memory.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/tutorbot/agent/memory.py#L229)：

- 长期事实写到 `PROFILE.md`
- 可 grep 的时间线日志写到 `SUMMARY.md`
- 当上下文窗口快爆掉时，按“用户轮次边界”挑一段旧消息做 consolidation，见 [memory.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/tutorbot/agent/memory.py#L265) 到 [memory.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/tutorbot/agent/memory.py#L368)
- consolidation 不是普通 prompt，而是要求模型调用 `save_memory` 工具，返回 `history_entry` 和 `memory_update`，见 [memory.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/tutorbot/agent/memory.py#L21) 到 [memory.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/tutorbot/agent/memory.py#L45)、[memory.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/tutorbot/agent/memory.py#L124) 到 [memory.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/tutorbot/agent/memory.py#L206)
- 连续失败 3 次后会降级成 raw archive，直接把原始消息刷进历史文件，见 [memory.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/tutorbot/agent/memory.py#L211) 到 [memory.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/tutorbot/agent/memory.py#L229)

它的 session 历史本身还是 JSONL，并且 `last_consolidated` 之前的消息虽然已归档，但不会真的从消息文件里删掉，只是在给 LLM 构建上下文时不再带上，见 [manager.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/tutorbot/session/manager.py#L16) 到 [manager.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/tutorbot/session/manager.py#L64)。

**6. 这个系统当前的特点和边界**
它的优点是简单、可读、可人工编辑、易调试。你直接看 `PROFILE.md` / `SUMMARY.md` 就知道模型“记住了什么”。  
但它当前也有明显边界：

- 没有向量化长期记忆检索，不能按语义召回某一条旧事实。
- 长期记忆是整篇重写，质量依赖 LLM。
- `deep_solve` 目前对共享记忆的使用偏弱，主入口仍是会话上下文；你可以看 [main_solver.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/agents/solve/main_solver.py#L850) 到 [main_solver.py](/Users/yangenhui/code/Github/yangeh03/TutorAgent/deeptutor/agents/solve/main_solver.py#L871)，它现在主要 merge 的是 `conversation_context`，而不是显式把 `PROFILE/SUMMARY` 深度接进去。
- 这更像“文件化长期记忆 + 会话摘要”，而不是完整的 memory retrieval system。

引导式学习虽然把每次 session 存下来了，但并不会自动把“这个学生在哪些知识点掌握较弱、偏好哪种引导方式、最近学到了什么”沉淀进全局长期记忆。

还有一个很重要的限制
它现在的 progress 不是“学生掌握度”，而更像“课程页面准备度 / 流程进度”。

当前进度计算逻辑是：ready 页面数 / 总知识点数，见 guide_manager.py (line 217) 到 guide_manager.py (line 224)。
也就是说，它记录的是：

哪些知识点页面生成好了
当前导航到哪个知识点
学习对话发生了什么
但它没有真正建一个“掌握度模型”，比如：

知识点 A：已掌握
知识点 B：反复提问，理解不稳
知识点 C：需要复习
用户偏好：喜欢先举例再抽象
这些目前都没有自动结构化保存成长期 learner profile。

所以结论是
有“持续记录学习进度”，但范围限于 guide session 本身。
没有“自动累积成学生长期学习记忆”的完整闭环。