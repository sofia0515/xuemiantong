
## 第一阶段：模型工厂

### 目标

创建统一的模型实例，把模型创建逻辑从业务代码中抽离出来，做到换模型只需改配置、加模型只需注册工厂，方便后续扩展。

### 完成内容

1. **配置中心（）**
   - 使用 `pydantic-settings` 定义 `Settings` 类，统一管理模型配置：
     `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL`、`DEEPSEEK_MODEL`、`DEEPSEEK_TEMPERATURE`、`DEEPSEEK_MAX_TOKENS`。
   - 通过 `python-dotenv` 自动加载 `.env`，配置项缺失时启动即报错，避免运行期才发现问题。
   - 全局导出单例 `settings`，其他模块统一引用，不重复读取环境变量。

2. **模型工厂()**
   - `LlmFactory`：模型构建函数类型别名，统一工厂函数签名。
   - `_build_deepseek_model()`：基于 `ChatOpenAI` 对接 DeepSeek 的 OpenAI 兼容接口。
   - `_PROVIDERS_FACTORY`：provider 到构建函数的注册表，新增模型只需追加一项。
   - `get_chat_model(provider="deepseek")`：对外统一入口。

### 关键设计

- **依赖倒置**：业务只依赖 `get_chat_model()`，不关心具体供应商。
- **可扩展**：新增供应商 = 新增构建函数 + 注册表加一行。
- **配置外置**：模型名、温度、max_tokens 均走环境变量。

---

## 第二阶段：提示词三层：公共模板、私有模板、用户变量注入

### 目标

打通「用户画像 → 提示词模板（版本化）→ Prompt 组装」,同时引入 MySQL + Redis 作为持久化与缓存底座。

### 完成内容

1. **持久化与缓存底座**
   - 定义两张核心表：一张存用户画像（目标岗位、经验、薄弱点、学习目标等），一张存提示词模板（支持版本自增、生效开关、公共/私有区分）。
   - 价值点：请求级 Session 避免串数据，JSON 字段灵活扩展画像结构，模板表为后续多智能体场景复用打基础。

2. **用户画像服务**
   - 提供画像读取接口，对缺失字段自动填充默认值，保证下游 Prompt 组装不会因空值崩掉。
   - 把画像中的 JSON 数组（技能列表、薄弱点等）格式化成自然语言文本，适配模板占位符的注入方式。
   - 价值点：画像数据从"存下来"到"能用起来"的关键一步，格式化逻辑集中管理，模板层只管占位符替换。

3. **提示词模板管理**
   - 支持模板的版本化管理：同一 agent + scene 可以有多条版本，`is_active` 控制当前生效版本。
   - 启动时把所有生效模板预热到 Redis，运行期优先从缓存读取，缓存 miss 自动回退 DB，Redis 挂了也不阻塞启动。
   - 公共模板与 agent 私有模板按场景拼接，既保证全局统一指令，又允许各 agent 按需定制。
   - 提供一键版本回滚能力。
   - 价值点：Prompt 改动能在线热更新，无需重启服务；Redis 自动降级策略保证了"缓存挂了 ≠ 服务挂了"。

4. **提示词组装**
   - 三层流水线：安全校验 → 格式规整 → 占位符注入，每一层职责单一。
   - 注入时对用户输入做 XSS 关键字过滤和长度截断，避免恶意内容污染 Prompt。
   - 对 Prompt 中的花括号做转义，防止 JSON 内容被 LangChain 误解析为变量占位符。
   - 价值点：把"Prompt 怎么拼"这一易变逻辑从对话链路中抽离，改 Prompt 不用改对话代码。

5. **启动预热**
   - 应用启动时自动把生效中的提示词模板批量写入 Redis，避免首个请求打到 DB。
   - Redis 不可用时自动跳过，不影响应用启动。
   - 价值点：冷启动即完成缓存预热，首个请求延迟从"查 DB + 写缓存"降到"纯读缓存"。

### 关键设计

- **三层 Prompt 组装**：验证 → 格式化 → 注入，每一层职责单一，便于单独替换或扩展。
- **公共 + 私有模板拼接**：`get_full_prompt()` 把场景级公共模板作为前缀，agent 私有模板追加，既保证全局统一指令又允许各 agent 定制。
- **Redis 自动降级**：`PromptTemplateManager.__init__` 里 try/except，Redis 挂了就 `self.use_redis = False`，后续所有读操作 fallback 到 DB，启动不受影响。


## 第三阶段：SSE 流式聊天，先占位再补全文

### 目标

在阶段二的 Prompt 组装之上，打通「会话校验 → 消息占位落库 → 流式生成 → 全量回写」的对话闭环，让前端通过 SSE 边生成边展示，同时保证异常中断也能留住已生成内容。

### 完成内容

1. **会话与消息持久化**
   - 新增 `sessions` 表：记录 `user_id`、`session_model`（0=学习，1=面试，2=笔记）、`title`。
   - 新增 `chat_messages` 表：记录 `request_id`、请求/响应正文、附件段（`request_segments` / `response_segments`）、结构化载荷、引用来源（`reference_sources`）、消息状态（`status`）、关联面试 `interview_id` 与文件提取文本。
   - 建立 `(session_id, created_at)` 联合索引，保证按会话拉历史消息走索引。
   - 价值点：正文与附件段分离存储，避免把图片/文件信息塞进聊天文本；引用来源结构化后便于前端展示"来源"入口。

2. **会话归属校验**
   - `SessionService.get_session_or_404()` 按 `user_id + session_id`（可选 `session_model`）查询，不存在直接抛 404。
   - 价值点：会话与用户绑定，防止越权读取他人会话；校验放在流式生成之前，避免无效请求占用模型资源。

3. **先占位再补全文**
   - 请求进入后先写入一条 `response_text=""` 的占位消息并提交，拿到自增 `row.id`。
   - 通过首帧 `start` 事件把 `message_id` 下发给前端，前端可立即完成乐观渲染与消息定位。
   - 生成结束后在 `finally` 中回写完整 `response_text` 与 `reference_sources`，无论正常结束还是异常中断都会落库。
   - 价值点：把"长耗时生成"和"消息唯一标识"解耦，前端不必等整段回复生成完才拿到消息 ID；断流时也能保留已生成的部分内容。

4. **SSE 事件协议**
   - `_sse_data()` 统一把事件对象编码为 `data: {...}\n\n`，使用 `ensure_ascii=False` 保证中文可读。
   - 事件类型：
     - `start`：`{message_id}`，流开始；
     - `delta`：`{text}`，文本增量；
     - `error`：`{message}`，生成异常；
     - `done`：`{response_text, sources}`，全量结果与引用来源。
   - `StreamingResponse` 声明 `text/event-stream`，并带 `Cache-Control: no-cache`、`Connection: keep-alive`、`X-Accel-Buffering: no`，避免代理层缓冲导致"假流式"。
   - 价值点：事件按 `type` 分发，前端只需处理四种事件即可完成整轮对话；`done` 携带全量文本，便于前端做最终校对与本地缓存。

5. **流式对话链路**
   - `build_stream_chain_context()` 返回 `(chain, stream_inputs)`，链路本身是 `prompt | llm`，无状态，历史消息由调用方通过 inputs 注入。
   - 有 `agent_name + scene` 时走个性化 Prompt（公共模板 + 私有模板 + 用户变量注入），否则使用通用兜底 Prompt。
   - system prompt 中的花括号统一转义，防止 JSON 内容被 `ChatPromptTemplate` 误解析为变量占位符。
   - `_extract_text_delta()` 只提取 `AIMessageChunk.content`，过滤掉非文本块与空增量。
   - 价值点：对话入口只关心"校验 + 落库 + 推送"，Prompt 结构与模型创建分别由阶段二和阶段一承担，后续接 RAG 或多 agent 时只改上下文构造。

### 关键设计

- **占位行先行**：消息 ID 在生成前就已确定，既是前端渲染锚点，也是后续历史记忆截断、引用来源回写的依据。
- **事件化协议**：`start / delta / error / done` 四类事件职责清晰，异常也以事件形式下发，前端不会因为连接中断而无从判断。
- **异常闭环**：`try/except` 只收集错误信息，统一在 `finally` 中落库，保证"出错也有一条完整消息记录"，`error` 事件先于 `done` 发送。

---

## 第四阶段：三层记忆（短期 / 工作 / 长期）

### 目标

解决长会话场景下"上下文越拉越长、Token 越烧越多、用户偏好越聊越模糊"三个问题，按数据新鲜度与保留时长分层，让每一轮对话只携带"必要的记忆"进入 Prompt。

### 分层模型

| 层级 | 介质 | 保留内容 | 生命周期 | 回答什么问题 |
|------|------|----------|----------|--------------|
| 短期记忆 | MySQL `chat_messages` | 最近 8 轮问答原文 | 永久（全量落库） | "刚才聊了什么" |
| 工作记忆 | Redis Hash | 最近 6 轮原文 + 滚动摘要 | TTL（按会话） | "当前任务的上下文" |
| 长期记忆 | MySQL `user_profiles` | 用户画像字段（目标/能力/偏好/面试） | 跨会话持久 | "这个用户是谁" |

### 完成内容

1. **短期记忆（冷启动 / 降级层）**
   - 从 `chat_messages` 按 `before_message_id` 游标倒序取最近 8 轮，转成 `HumanMessage / AIMessage` 列表。
   - 两级裁剪：DB 候选集先按字符预算筛，进入 Prompt 前再做一次兜底裁剪，从最老开始成对丢弃，保证 user / assistant 不错位。
   - 价值点：作为 Redis 失效或冷启动时的兜底，历史永远可从库中重建，不依赖缓存存活。

2. **工作记忆（热路径 / 压缩层）**
   - Redis Hash 存 `raw`（最近 6 轮原文）+ `summary`（滚动摘要），键按 `user_id:session_id` 隔离，每次读取续期 TTL。
   - 追加轮次时若原文总字符超预算，触发**滚动摘要**：旧轮次交给轻量模型合并进既有摘要，只保留最近 6 轮原文，摘要单条上限 500 字，防止"越合并越长"。
   - 注入时摘要以 `SystemMessage` 前置，原文以 `Human/AIMessage` 排列在 `MessagesPlaceholder`。
   - 价值点：热路径不碰 DB，Redis 命中即返回；超长对话用"摘要替代原文"把 Token 压到常数级，会话切换时主动 `clear` 释放。

3. **长期记忆（画像层）**
   - 复用阶段二的 `user_profiles` 表，按字段分组：`goal`（目标岗位/级别/经验/学习目标）、`ability`（技能/薄弱点）、`preference`（学习偏好）、`interview`（面试重点）。
   - **读取意图判定**：正则规则优先识别"结合我的情况/薄弱点/目标"类请求，命中才加载画像并按字段分组拼接 SystemMessage；未命中则不注入，避免每轮都把完整画像塞进 Prompt。
   - **写入意图判定**：识别"我是 X 年经验 / 我薄弱点是 Y / 记住 Z"类陈述，标记为需要异步抽取更新（当前规则兜底，轻量模型分类为 TODO）。
   - 价值点：画像只在"该用"时注入，回答结束后"该记"的事实异步回写，读写都不阻塞主链路。

4. **统一上下文装配**
   - `MemoryService.load_context()` 是唯一出口：优先读 Redis 工作记忆 → 空则回退 MySQL 短期记忆 → 再按需拼接长期画像。
   - 装配出的 `SystemMessage`（摘要 + 画像）从 history 列表中剥离，单独拼到 `system_prompt`，保证 `MessagesPlaceholder` 里只留 user / assistant 对。
   - 价值点：对话链路 `prompt | llm` 保持无状态，记忆策略变化（换介质、改预算、加分层）不影响对话代码。

### 关键设计（生产级要点）

- **介质分级**：热数据放 Redis（快、易失），冷数据放 MySQL（慢、可靠），画像单独建表（结构化、可复用）。三级各司其职，不互相替代。
- **预算驱动裁剪**：短期记忆 DB 候选预算 + Prompt 兜底预算双层控制，成对裁剪防止角色错位；工作记忆用滚动摘要把长会话 Token 压到常数级。
- **降级而非阻断**：Redis 异常返回空结构，主链路自动回退 MySQL；任何一层挂了都不影响出回答，只影响"记忆密度"。
- **读写分离**：读路径同步装配进 Prompt；写路径（画像更新、工作记忆追加）在生成成功后触发，避免拖慢首 token 延迟。
- **意图门控**：长期画像"按需注入"而非"每轮全量注入"，既省 Token 又避免无关节污染。


## 第五阶段：RAG（检索增强生成）

### 目标

让 AI 回答"有据可依"：用户上传的简历 / 学习资料不再只是附件，而是可以被语义检索的知识源。核心分工——**Qdrant 负责"像不像"，MySQL 负责"原文是什么"**。

### 摄入链路（离线建库）

上传时：解析 → 清洗 → 分类 → 分块去重 → 向量化 → 写 Qdrant + 备份 MySQL。

1. **解析**
   - 按扩展名分派解析器：PDF 走 pypdfium2，DOCX 走 python-docx（按大纲级别注入 Markdown 标题），TXT 直接读。
   - 扫描版 PDF 兜底：平均每页字符 < 20 判定为扫描件，走火山 OCR。
   - 统一清洗：去零宽字符 / 合并空白 / 压缩连续换行 / 删除独立页码行。
   - 价值点：同一套文本管线，新增格式只需在解析器注册表加一行。

2. **分类**
   - 显式指定值优先 → 内容关键字计分（简历词 / 学习资料词）→ `general` 兜底。
   - 检索时可按 `doc_category` 过滤，缩小向量检索范围。

3. **分块**
   - 递归字符切片：分隔符优先级 `标题 → 段落 → 句子 → 标点 → 字符`，尽量保留语义结构。
   - 默认 `chunk_size=500 / overlap=50 / 最小块长=20`，过短块丢弃。
   - MD5 指纹去重，避免同一文档重复段落进向量库。

4. **向量化**
   - DashScope `text-embedding-v4`，1024 维，单次最多 10 条分批调用，按 `text_index` 还原顺序。
   - **入库侧 `text_type=document`，查询侧 `text_type=query`**——两个角色向量空间不同，混用会显著掉精度。

5. **写入双库**
   - Qdrant：每个块生成 UUID 作为 Point id，payload 只存 `user_id / doc_category / file_name / chunk_index` 等过滤字段，**不存原文**以节省向量库存储。
   - MySQL `knowledge_chunks`：存 `resource_id / chunk_index / text / char_count / vector_id`，是原文权威来源。
   - 同一 `(user_id, file_name)` 重复上传时**先删后写**，避免新旧点并存导致检索重复。
   - 事务保证：Qdrant 写成功但 MySQL 备份失败时回滚，防止"向量能命中但回查不到原文"。

### 检索链路（在线问答）

用户提问时：意图门控 → 问题向量化 → 向量检索 → 回查原文 → 分数过滤 → 格式化注入 Prompt。

1. **意图门控**
   - `should_retrieve()`：正则跳过"好的 / 继续 / 谢谢"等确认语、推进语、极短输入，其余默认检索。
   - 画像写入意图优先判定：命中"我是 X 年经验"类陈述时跳过 RAG，避免检索结果干扰画像抽取。
   - 价值点：省掉无信息量轮次的 embedding 调用和向量检索开销。

2. **两步检索**
   - 第一步：Qdrant `query_points` 按 `user_id` 强制过滤（可选 `doc_category`），取 top_k。
   - 第二步：用返回的 `vector_id` 批量回查 MySQL 拿原文。
   - 集合不存在（用户从未上传资料）时直接返回空，不中断聊天主流程。

3. **后置过滤**
   - **分数阈值过滤**：低于 0.4 的命中直接丢弃，防止"Qdrant 永远返回 top_k"把无关片段塞进 Prompt。
   - **单条截断**：单条片段超 800 字符截断，防止一块吃掉整个上下文预算。

4. **注入 Prompt**
   - `format_retrieved_chunks()` 拼成 `【参考资料】[来源 1] 文件：xxx\n...` 格式，前置在用户问题前。
   - `build_rag_system_prompt()` 同步注入"优先基于参考资料回答 / 没有就说不知道 / 引用时附来源引导语"规则。
   - 检索结果通过 SSE `done` 事件的 `sources` 下发前端，同时 `source_refs`（`chunk_id + score`）落库到 `chat_messages.reference_sources`，支持会话恢复时重建来源列表。

### 模型回答后处理

流式生成结束后（`finally` 块，无论成功或异常都触发）按序执行以下四步，与主对话链路解耦：

1. **对话记录落库 MySQL**
   - 把流式累计的 `response_text` 回写到占位行，同时把 `reference_sources`（`chunk_id + score`）落库。
   - 占位行在请求进入时就已创建（第三阶段），此处只更新字段，不新建记录，保证断连时消息 ID 不变。

2. **工作记忆追加到 Redis**
   - 生成成功且无异常时，调用 `append_turn(user_msg, ai_msg)` 把本轮原文追加进工作记忆。
   - 超过字符预算时触发滚动摘要（第四阶段已实现），旧轮次压缩为摘要、只保留最近 6 轮原文。

3. **画像更新意图判定 + 异步抽取**
   - 先用规则判定本轮是否命中"我是 X / 我薄弱点是 Y / 记住 Z"类陈述，命中则丢进后台线程池（`ThreadPoolExecutor`，4 并发）。
   - 后台线程独立开 DB Session，调用大模型按 `PROFILE_UPDATE_PROMPT` 抽取画像字段（输出 JSON），再按字段类型合并入库：
     - 数组字段（技能/薄弱点/面试重点）：去重、截断上限、覆盖旧值；
     - 文本字段（岗位/经验/偏好/摘要）：非空覆盖，摘要限 500 字；
     - 岗位级别正则兜底补抽，防止模型漏抽。
   - **关键**：整个异步链路不阻塞 SSE 流，用户不会因为画像抽取延迟看到回答变慢；后台线程独立 DB Session + `with_for_update()` 行锁，避免与主请求事务冲突。

4. **参考资料双通道下发**
   - `done` 事件携带 `sources`（含 `chunk_id / resource_id / file_name / score / text`）供前端即时展示"来源"入口。
   - `source_refs`（仅 `chunk_id + score`）落库到 `chat_messages.reference_sources`，前端刷新或断连重连后可按 `chunk_id` 回查 `knowledge_chunks` 表重建来源列表，不依赖 SSE 长连接存活。

### 扫描版 PDF OCR 兜底

- **触发条件**：pypdfium2 抽取后平均每页字符 < 20，或整份文档零字符，判定为扫描件。
- **兜底路径**：调用火山引擎 OCR（`volc_access_key / volc_secret_key / volc_region`）逐页识别，输出文本继续走同一套清洗 → 分块 → 向量化管线。
- **价值点**：纯文字 PDF 走本地 pypdfium2（快、免费），扫描件才触发 OCR（慢、按量计费），按页数均字符数自动分流，避免所有 PDF 都走 OCR 造成成本浪费。
- **TODO**：`ocr.py` 当前为空壳，火山 OCR 调用待接入；接入后需补充 OCR 文本的清洗规则（OCR 常带噪点字符、表格识别错乱等）。

### 关键设计（生产级要点）

- **职责分离**：向量库只存过滤字段和向量，原文权威在 MySQL——向量库重建或换库时原文不丢，payload 膨胀问题也规避了。
- **先删后写**：重复上传同一文件不会产生新旧点混用，检索结果干净。
- **事务边界**：Qdrant 先写成功后 MySQL 备份，失败回滚 MySQL；向量删除补偿（按 id 过滤删旧点）目前为 TODO，需对账任务兜底。
- **降级策略**：集合不存在 / 检索异常 / 无命中都返回空，聊天链路始终可用，只是"没有参考资料"。
- **预算控制**：检索 top_k=3、分数阈值 0.4、单条截断 800 字，三层限制保证 RAG 不会把上下文吃光。
- **双向关联**：UUID 同时作为 Qdrant Point id 和 MySQL `vector_id`，检索结果和原文一一对应，无需额外映射表。


## 第六阶段：LangGraph 学习测评工作流（出题 → 中断 → 交卷 → 评分）

### 目标

把"出题 → 等用户作答 → 评分"这套跨多轮请求的业务流程，从"一次性 HTTP 调用"改成"可中断、可恢复、状态可落库"的图执行。核心问题：用户从看到题目到交卷可能间隔几分钟，HTTP 请求早已结束，必须把图状态持久化，等用户交卷时再从断点恢复。

### 图结构

四个节点串行，唯一分支是中断：

```
generate_quiz → wait_user_answer(interrupt) → evaluate_answer → finalize_result → END
```

- `generate_quiz`：调用大模型出题，产出 `quiz` 结构（标题、描述、题目列表），状态置为 `waiting_answer`。
- `wait_user_answer`：调用 `interrupt()` 把 quiz 抛给前端，**图执行在此挂起**，等待下次 `Command(resume=answers)` 唤醒。
- `evaluate_answer`：拿到用户答案后，调用大模型评分，产出 `score / items / weaknesses / review / display_text`。
- `finalize_result`：收尾，状态置为 `completed`。

### 完成内容

1. **状态模型（Pydantic）**
   - `LearningWorkflowState`：`run_id / user_id / session_id / request_text / question_count / quiz / answers / evaluation / score / weaknesses / review / status`。
   - `WorkflowStatus` 枚举：`created → generating_quiz → waiting_answer → grading → completed / failed`。
   - 价值点：图节点之间通过强类型状态传递，字段缺省有默认值，不会因为少传字段崩掉。

2. **Checkpoint 机制**
   - `MemorySaver` 进程内共享单例（`lru_cache`），按 `thread_id` 隔离不同 run。
   - `build_thread_config(run_id)` 统一生成 `{"configurable": {"thread_id": run_id}}`，图恢复时必须传同一 config。
   - 价值点：中断后图状态自动序列化到 checkpointer，下次 `invoke(Command(resume=...), config)` 从断点继续，不重跑出题节点。

3. **出题节点**
   - 动态 Prompt：优先从提示词模板表取 `quiz_generate_workflow` 模板，取不到走硬编码兜底。
   - 模板渲染用简单字符串替换（`{request_text}` / `{question_count}`），避免 JSON 示例中的 `{}` 被 `str.format` 误解析。
   - 模型输出 JSON 清洗：`extract_json_object()` 去掉 Markdown 代码块围栏，再用正则截取首个 `{...}` 对象。
   - 题目合法性过滤：只接受 `radio / checkbox / textarea` 三种题型，其余丢弃。

4. **中断节点**
   - `interrupt({"quiz": ...})` 把 quiz 作为中断值抛给调用方，**图执行暂停**。
   - 前端拿到 quiz 后渲染表单，用户交卷时把答案列表作为 `Command(resume=answers)` 的输入唤醒图。
   - 价值点：出题和评分解耦在两个 HTTP 请求里，中间用户思考多久都行，不占连接、不占模型。

5. **评分节点**
   - 动态 Prompt：优先取 `learning_evaluator` 模板，拼接 quiz JSON 和 answers JSON，再追加"display_text 必须包含总分、逐题点评、参考答案、薄弱点、学习建议"的补充约束。
   - 分数钳制：`score = max(0, min(score, 100))`，防止模型输出越界。
   - 输出收敛：`display_text` 优先，其次 `review`，最后兜底文案，保证前端总有内容可展示。

6. **工作流运行记录（MySQL 持久化）**
   - `workflow_runs` 表：`run_id / user_id / session_id / workflow_type / status / state_json / error_message / completed_at`。
   - `state_json` 存完整状态 dict，即使进程重启 / checkpointer 丢失，也能从 MySQL 重建。
   - 索引：`(user_id, workflow_type, status)` 查用户运行列表，`(session_id, workflow_type)` 查会话下的工作流。
   - 价值点：checkpointer（内存）只负责图执行断点，MySQL 负责业务可追溯，两者互补。

7. **服务层封装**
   - `LearningWorkflowService.start()`：校验会话 → 创建 run 记录 → 出题（带重试）→ 更新状态为 `waiting_answer` → 写入一条 `chat_messages`（`response_payload` 携带 quiz 表单）。
   - `submit_answer()`：按 `run_id` 查 run → 校验状态是 `waiting_answer` → 提交答案恢复图 → 评分（带重试）→ 更新状态为 `completed` → 原地更新同一条 `chat_messages`（把表单 payload 换成点评文本）。
   - 价值点：前端历史列表里只看到一条消息，出题时是表单，交卷后原地变成点评，不出现"出题一条、评分一条"的重复。

8. **自动重试**
   - `RetryExecutor`：默认最多 2 次，失败时把 `auto_retry_count / last_auto_retry_node` 写回状态。
   - 出题或评分失败时先重试一次，仍失败则 `mark_failed()` 把状态置为 `failed` 并记录 `error_message`。

### 关键设计（生产级要点）

- **中断即挂起**：`interrupt()` 不是普通返回，图执行状态被 checkpointer 冻结，恢复时从断点继续，不重跑已完成节点。这是 LangGraph 区别于"一次性函数调用"的核心能力。
- **双通道持久化**：内存 checkpointer 管图执行断点（快、易失），MySQL `workflow_runs` 管业务状态（慢、可靠）。进程重启后 checkpointer 丢失，但 MySQL 里有完整状态，可以重建。
- **状态即契约**：节点之间只通过 `LearningWorkflowState` 通信，不共享全局变量；Pydantic 保证字段类型和默认值。
- **原地更新消息**：出题和评分共用同一条 `chat_messages`，`request_id = "{run_id}:quiz"`，交卷后 `response_payload` 从表单换成 `None`、`response_text` 换成点评文本，前端历史列表无重复。
- **模板优先、硬编码兜底**：Prompt 模板从 DB 取，取不到用代码里的硬编码版本，保证"模板表为空时图也能跑"。
- **失败可追溯**：`mark_failed()` 记录失败节点和错误信息，`state_json.status = failed`，前端可据此展示"出题失败，请重试"。

### 待补齐

- Checkpointer 当前是 `MemorySaver`（进程内存），多实例部署或重启会丢失断点，需换 Redis / PostgreSQL checkpointer。
- 超时机制：用户中断后一直不交卷，run 记录永久停在 `waiting_answer`，需要定时任务清理或过期失效。
