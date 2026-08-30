# AI 生成流程图本地 MVP：15 日完整开发计划

## 一、项目目标

基于当前 `test` 分支开发，不修改 `master`，交付一个本地可部署运行的 AI 流程图应用：

- 当前真实生成默认使用 DeepSeek 官方 API，默认模型为 `deepseek-v4-flash`，同时适配 Chat Completions 和 Responses API。
- 支持 Anthropic Messages API。
- 支持 OpenAI Chat Completions API。
- 支持 OpenAI Responses API。
- 支持标准 OpenAI-compatible 第三方中转站。
- 支持供应商自动路由和用户手动选择模型。
- 使用 Celery + Redis 执行本地异步任务。
- 使用 React Flow 编辑流程图，dagre 自动布局。
- 支持文档保存、刷新恢复、取消、重试。
- 支持 SVG、PNG、Mermaid、JSON 导出。
- 使用 PostgreSQL、Redis、MinIO 和 Docker Chromium Worker。
- 保留 AI 应用广场认证、额度、用量上报的适配接口，但本轮不进行真实广场联调。

## 二、Git 管理规范

### 2.1 分支规则

- 开发基线固定为 `test`，跟踪 `origin/test`。
- 每日创建一个独立功能分支。
- 每日分支命名：`feat/dXX-short-name`。
- MR 目标分支固定为 `test`。
- 本轮禁止修改、推送或合并到 `master`。
- 下一日必须等待上一日 MR 合入 `test` 后，再从最新 `origin/test` 创建分支。

每日开始：

```powershell
git switch test
git pull --ff-only origin test
git switch -c feat/dXX-short-name
```

### 2.2 每个需求的提交与推送流程

每日计划表中的每一个提交项都视为一个独立需求，固定执行：

1. 实现该需求。
2. 同步增加对应测试。
3. 运行该需求的定向测试。
4. 执行 `git diff --check`。
5. 检查 `git diff` 和 `git status --short`。
6. 只暂存该需求相关文件。
7. 创建一次原子提交。
8. 立即推送当前每日功能分支。
9. 在 MR 中记录测试结果。

不允许将多个无关需求合并成一个提交，也不允许积攒到当天结束再统一推送。

提交格式：

```text
feat: 新增业务能力
fix: 修复缺陷
test: 增加测试
docs: 更新文档
chore: 工程或依赖配置
```

### 2.3 使用 Git Push Options 创建 MR

每日第一个需求提交后，自动创建目标为 `test` 的 Draft MR：

```powershell
git push --set-upstream origin feat/dXX-short-name `
  --push-option=merge_request.create `
  --push-option=merge_request.target=test `
  --push-option=merge_request.draft `
  --push-option=merge_request.remove_source_branch `
  --push-option="merge_request.title=DXX: 当日开发主题"
```

若自建 GitLab 不支持 `merge_request.draft`，则使用：

```powershell
git push --set-upstream origin feat/dXX-short-name `
  --push-option=merge_request.create `
  --push-option=merge_request.target=test `
  --push-option=merge_request.remove_source_branch `
  --push-option="merge_request.title=Draft: DXX 当日开发主题"
```

后续需求完成后：

```powershell
git push origin feat/dXX-short-name
```

所有后续推送都会更新同一个 MR。

### 2.4 每日合并门槛

每日结束后：

1. 运行当日全量测试。
2. 检查 MR 文件范围和提交记录。
3. 在 GitLab 网页补充测试结果。
4. 将 Draft MR 标记为 Ready。
5. 合入 `test` 前单独获得用户确认。
6. 使用普通 Merge，保留原子提交，不 squash。
7. 合并后删除远端功能分支。

禁止强制推送、直接推送 `test`、提交密钥或修改已执行迁移。

## 三、逐日开发计划

| 天数与分支 | 独立需求提交，每项完成后立即推送 | 当日验收 |
|---|---|---|
| D01 `feat/d01-project-baseline` | `chore: 初始化AI流程图前后端依赖`；`fix: 修正Umi和FastAPI本地启动配置`；`chore: 新增本地全栈Compose骨架`；`feat: 建立流程图工作台入口` | admin 登录、健康检查、前端构建、Compose 配置通过；商品和权限演示入口隐藏但代码保留。 |
| D02 `feat/d02-domain-model` | `feat: 定义DiagramDocument领域契约`；`feat: 定义任务供应商和导出契约`；`feat: 新增AI流程图业务表迁移`；`feat: 新增内置流程模板种子`；`feat: 补充任务浏览器会话恢复字段` | V5/V6 可从已有 V1-V4 正常升级；后续 V7 可从 V1-V6 增量升级，旧任务允许 `session_id` 为空；恢复查询始终按 `user_id` 隔离，Schema 边界测试通过。 |
| D03 `feat/d03-diagram-engine` | `feat: 实现DiagramDocument校验器`；`feat: 实现安全Mermaid编译器`；`test: 增加流程图安全与边界测试` | 六类节点、TB/LR、循环边、节点与连线限制、脚本转义测试通过。 |
| D04 `feat/d04-provider-core` | `feat: 实现供应商配置清单加载`；`feat: 实现Provider注册中心和统一协议`；`feat: 实现统一httpx传输层`；`feat: 提供供应商公开列表接口` | 配置校验、能力筛选、超时和日志脱敏测试通过；响应不暴露 Key 和 Base URL。 |
| D05 `feat/d05-anthropic-provider` | `feat: 实现Anthropic Messages适配器`；`feat: 实现Anthropic结构化输出约束`；`feat: 实现Anthropic响应解析和错误映射` | 成功、401、429、5xx、超时、内容拒绝、空结果和非法 JSON 契约测试通过。 |
| D06 `feat/d06-openai-chat-provider` | `feat: 实现OpenAI Chat Completions适配器`；`feat: 适配DeepSeek Chat Completions请求与响应`；`feat: 实现DeepSeek JSON模式和严格JSON提示词`；`test: 增加OpenAI Chat与DeepSeek Chat契约测试` | DeepSeek `POST /chat/completions` 使用 `deepseek-v4-flash`，同时发送 `response_format: {"type":"json_object"}` 和明确 JSON 指令；官方地址、OpenAI 官方地址和兼容 Base URL 均可复用同一适配器。 |
| D07 `feat/d07-openai-responses-routing` | `feat: 实现OpenAI Responses适配器`；`feat: 适配DeepSeek无状态Responses API`；`feat: 支持第三方中转站配置`；`feat: 实现自动优先级路由`；`feat: 实现用户手动模型选择和安全降级` | DeepSeek `POST /responses` 使用 `deepseek-v4-flash` 和 `text.format` 结构化输出，不发送官方未支持的状态参数；Chat、Responses、中转站、自动路由和有限降级测试通过。 |
| D08 `feat/d08-task-api` | `feat: 实现生成任务创建和查询`；`feat: 实现任务幂等控制`；`feat: 实现任务取消和重试`；`feat: 实现用户资源隔离和业务错误码` | 创建接口 1 秒内返回 taskId；重复提交不重复调用供应商；非本人访问被拒绝。 |
| D09 `feat/d09-celery-engine` | `feat: 接入Celery Worker和Beat`；`feat: 实现本地任务状态机`；`feat: 实现供应商调用任务`；`feat: 实现超时取消重试和补偿扫描` | 成功、失败、超时、取消均能进入确定终态；真实调用失败不切换 Mock。 |
| D10 `feat/d10-task-events` | `feat: 实现Redis任务事件发布`；`feat: 实现任务SSE接口`；`feat: 实现前端SSE和轮询降级`；`feat: 实现任务刷新恢复和离开确认` | SSE 断开后每 2 秒轮询；刷新不重复提交；任务结束后停止监听。 |
| D11 `feat/d11-workbench-ui` | `feat: 实现流程图工作台布局`；`feat: 实现描述输入和内置模板`；`feat: 实现方向粒度和模型选择`；`feat: 实现任务状态栏和异常反馈`；`feat: 增加Provider加载失败非阻塞通知`；`feat: 增加Provider错误码友好中文映射和网络配置提示` | 空态、提交、处理、成功、失败、取消、无模型状态均具备中文反馈；Provider 加载失败时显示黄色非阻塞通知“当前默认供应商响应异常，正在尝试降级/路由”；`provider_unavailable` 显示“上游服务繁忙，请稍后重试”；不阻塞工作台输入，不暴露 Key 或 Base URL。 |
| D12 `feat/d12-canvas-editor` | `feat: 实现React Flow六类节点`；`feat: 实现节点和连线编辑`；`feat: 实现dagre自动布局`；`feat: 限制节点坐标和fitView范围`；`feat: 实现撤销重做和脏状态`；`feat: 使用zundo限制撤销重做历史快照`；`feat: 实现Mermaid只读预览窗格` | 50 节点、100 连线内可正常拖拽、缩放、编辑、布局和撤销；布局后节点 X/Y 均限制在 `[-10000, 10000]`，并在节点渲染完成后调用 `fitView({ padding: 0.2, minZoom: 0.5, maxZoom: 1.5 })`；历史最多保留 30 个快照。 |
| D13 `feat/d13-document-storage` | `feat: 实现文档查询和保存`；`feat: 实现文档版本乐观锁`；`feat: 实现保存后异步Mermaid编译状态`；`feat: 实现MinIO存储适配器`；`feat: 实现Mermaid和JSON导出` | 正式保存只接收 `diagramData`，先完成版本落库再异步编译 Mermaid；编译失败不回滚已保存的流程图数据，预览显示友好失败状态；版本冲突返回最新文档；导出文件具有用户归属和有效期。 |
| D14 `feat/d14-render-security` | `feat: 构建Chromium导出Worker`；`chore: 安装导出字体并刷新字体缓存`；`feat: 固定Chromium导出超时和进程清理`；`feat: 实现SVG导出`；`feat: 实现PNG导出`；`feat: 实现鉴权下载和过期清理`；`feat: 预留广场身份额度和用量接口` | 中文字体不出现方块；Chromium 渲染超时 30 秒后终止页面和浏览器进程并返回 `EXPORT_RENDER_FAILED`；四类导出有效；非本人无法下载；过期文件被清理；本地模式不调用广场。 |
| D15 `feat/d15-provider-integration` | `test: 完成DeepSeek Chat Completions真实联调`；`test: 完成DeepSeek Responses真实联调`；`test: 完成DeepSeek完整生成链路验收`；`feat: 清理等待或提交超时的僵尸任务`；每个问题分别使用 `fix(provider): ...` 提交；最后提交 `docs: 完善本地部署和供应商配置手册` | DeepSeek Chat、Responses 各完成一条真实短请求，默认链路使用 `deepseek-v4-flash`；Beat 将 `waiting`、`submitting` 且创建超过 1 小时的任务置为 `expired`；画布编辑、保存、刷新、取消、重试和四类导出全部通过；其他 Provider 完成 Mock 契约测试，不作为本轮真实联调门槛。 |

## 四、固定接口与公共类型

### 4.1 API 路径

严格遵循当前 Scaffold 规范：只使用 GET 和 POST，ID 通过 query 参数传递。

```text
GET  /api/flowchart/providers/list
GET  /api/flowchart/templates/list

POST /api/flowchart/tasks/create
GET  /api/flowchart/tasks/get?taskId=...
GET  /api/flowchart/tasks/list?sessionId=...
GET  /api/flowchart/tasks/events?taskId=...
POST /api/flowchart/tasks/cancel?taskId=...
POST /api/flowchart/tasks/retry?taskId=...

GET  /api/flowchart/documents/get?documentId=...
POST /api/flowchart/documents/save?documentId=...
POST /api/flowchart/documents/export?documentId=...

GET  /api/flowchart/files/download?fileId=...
```

### 4.2 创建任务请求

```json
{
  "type": "diagram_generate",
  "prompt": "用户提交请假申请，主管审批",
  "direction": "TB",
  "detailLevel": "standard",
  "providerId": null,
  "model": null,
  "sessionId": "浏览器生成的随机UUID",
  "idempotencyKey": "客户端生成的随机UUID"
}
```

规则：

- `prompt` 长度为 1-4000。
- `direction` 只允许 `TB`、`LR`。
- `detailLevel` 只允许 `concise`、`standard`、`detailed`。
- 新版工作台创建任务时必须传入 `sessionId`；它只用于同一浏览器会话的恢复关联，不能替代后端 `user_id` 的资源授权。
- 页面本地任务 ID 丢失时，先按 `sessionId` 查询未结束任务；没有命中时按当前登录用户查询最近未结束任务，避免任务成为孤儿。
- `providerId` 为空时自动路由。
- 前端模型选择器显示 Provider 的 `displayName`，提交时将对应值写入 `model`。
- 同一模型存在多个协议配置时，前端按 `displayName` 合并为一个模型选项，并保持 `providerId` 为空，由后端按路由规则选择具体协议。
- 用户指定 Provider 后，不得私自切换到其他 Provider。
- 重试接口始终创建新任务和新幂等键。

### 4.3 DiagramDocument

固定节点类型：

```text
start
end
process
decision
input_output
subprocess
```

固定限制：

- 标题不超过 100 字符。
- 节点不超过 50 个。
- 连线不超过 100 条。
- 节点标签不超过 120 字符。
- 节点 ID 在文档内唯一。
- 连线 `source`、`target` 必须指向存在节点。
- 合法循环边允许存在。
- HTML、脚本、事件属性和 Mermaid 特殊字符必须转义。

`diagramData` 是唯一权威数据。`mermaidSource` 只能由后端编译，正式保存接口不接受客户端直接覆盖。

- 正式保存请求只提交 `diagramData` 和乐观锁版本，不提交客户端 `mermaidSource`。
- 保存先持久化已通过 Schema 校验的 `diagramData` 并递增版本，再由 Celery 异步编译 Mermaid；编译状态写入已有 `flowchart_event.payload`，不新增跨表外键。
- Mermaid 编译成功时才更新 `mermaid_source`；编译失败不得回滚已保存的 `diagramData`，文档查询返回最近一次成功源码和脱敏的编译状态。
- `force_save_mermaid` 不属于正式前端 API 契约；仅允许在本地调试开关明确开启时由服务端调试工具使用，非本地模式和普通用户请求一律拒绝。

### 4.4 任务状态

```text
waiting
submitting
provider_queued
provider_processing
validating
rendering
success
failed
canceled
expired
```

终态为：

```text
success
failed
canceled
expired
```

任务进度只能前进，不能倒退。

### 4.5 统一响应

```json
{
  "code": 200,
  "data": {},
  "message": "操作成功",
  "errorCode": null,
  "timestamp": 1783072800000
}
```

固定业务错误包括：

```text
PROMPT_EMPTY
PROMPT_TOO_LONG
PROVIDER_NOT_CONFIGURED
PROVIDER_UNHEALTHY
PROVIDER_UNAVAILABLE
PROVIDER_AUTH_FAILED
PROVIDER_RATE_LIMITED
PROVIDER_SUBMIT_FAILED
PROVIDER_TASK_TIMEOUT
DIAGRAM_SCHEMA_INVALID
DIAGRAM_NODE_LIMIT_EXCEEDED
DIAGRAM_EDGE_INVALID
MERMAID_RENDER_FAILED
DOCUMENT_VERSION_CONFLICT
EXPORT_FORMAT_UNSUPPORTED
EXPORT_RENDER_FAILED
TASK_CANCELED
TASK_EXPIRED
```

## 五、固定实现契约

### 5.1 Provider 配置

提交非敏感模板：

```text
backend/config/providers.example.json
```

本地实际配置：

```text
backend/config/providers.local.json
```

`providers.local.json` 必须加入 `.gitignore`，配置路径通过 `AI__PROVIDERS_FILE` 指定。

当前默认真实 Provider 使用 DeepSeek 官方 API，并复用 `openai_compatible` 适配器。适配依据：

- [DeepSeek Chat Completions API](https://api-docs.deepseek.com/zh-cn/api/create-chat-completion)
- [DeepSeek Responses API](https://api-docs.deepseek.com/zh-cn/guides/responses_api)

Chat Completions 配置：

```text
providerId: deepseek-official-chat
displayName: deepseek-v4-flash
adapter: openai_compatible
protocol: openai_chat_completions
baseUrl: https://api.deepseek.com
model: deepseek-v4-flash
apiKeyEnv: DEEPSEEK_API_KEY
```

Responses 配置：

```text
providerId: deepseek-official-responses
displayName: deepseek-v4-flash
adapter: openai_compatible
protocol: openai_responses
baseUrl: https://api.deepseek.com
model: deepseek-v4-flash
apiKeyEnv: DEEPSEEK_API_KEY
```

两个配置共用同一环境变量和前端显示名称，但分别执行 `POST /chat/completions` 和 `POST /responses`。`model`、启用状态和优先级仍由配置文件管理，不在业务代码中硬编码；当前默认模型固定为 `deepseek-v4-flash`。

每个 Provider 固定字段：

```text
providerId
displayName
adapter
protocol
baseUrl
model
apiKeyEnv
capabilities
enabled
allowManualSelection
priority
timeoutSeconds
taskTimeoutSeconds
maxOutputTokens
```

枚举：

```text
adapter: anthropic | openai_compatible

protocol:
anthropic_messages
openai_chat_completions
openai_responses
```

API Key 只通过 `apiKeyEnv` 指向的环境变量读取。前端、数据库和公开配置文件不得保存 Key。

字段展示规则：

- `providerId` 是后端稳定唯一标识，用于路由、任务记录和接口传参，不在普通前端界面展示。
- `displayName` 必须直接复用同一配置的 `model` 值，不维护另一套展示名称。
- 修改 `model` 时必须同步修改 `displayName`；Provider 配置加载校验应拒绝两者不一致的配置。
- 多个 Provider 配置使用同一个 `model` 时，公开列表可保留各自 `providerId`，前端模型选择器按 `displayName` 去重展示。

### 5.2 Provider 统一协议

内部统一接口保留：

```text
submit
poll
cancel
healthCheck
```

本轮真实供应商均按同步 HTTP 响应实现，由 Celery 包装成本地异步任务。

- `submit` 返回统一 `ProviderSubmission`。
- 本轮返回模式固定为 `sync`。
- DeepSeek Chat 和 Responses 请求均固定使用 `stream: false`；前端 SSE 只传递本地任务事件，不直接透传供应商事件流。
- `poll`、`cancel` 保留扩展接口，但不实现供应商原生异步任务。
- 本地取消只保证任务不再保存或推进结果；已经发出的供应商 HTTP 请求采用尽力终止。

### 5.3 结构化输出

- DeepSeek Chat Completions 请求使用 `response_format: {"type":"json_object"}`，并在 system 或 user 消息中明确要求只生成 JSON；缺少任一条件均视为实现错误。
- DeepSeek Chat 只读取 `choices[0].message.content` 作为候选 JSON；`finish_reason="length"` 视为输出不完整，不保存文档。
- DeepSeek Responses 请求使用 `text.format` JSON Schema 约束，解析最终 `output_text`；所有结果仍必须再次通过 Pydantic DiagramDocument 校验。
- DeepSeek Responses 按官方无状态契约实现，不发送或依赖 `previous_response_id`、`conversation`、`store`、`background`、`metadata`、`include`、`prompt`、`truncation`、`context_management` 和 `stream_options`。
- OpenAI Chat 优先使用原生 JSON Schema 结构化响应。
- OpenAI Responses 优先使用 Responses 的结构化输出能力。
- Anthropic 优先使用工具约束或等价结构化能力。
- 中转站不支持原生结构化能力时，使用固定 JSON 提示词。
- 允许从 Markdown 代码块中提取单一 JSON 对象，但禁止执行任何内容。
- 所有结果最终必须通过 Pydantic DiagramDocument 校验。
- 模型返回的 Mermaid、HTML、解释文本和思维过程不作为权威数据。

### 5.4 供应商路由与降级

1. 过滤未启用、缺少 Key、能力不匹配的 Provider。
2. 自动模式按 `priority` 从高到低选择。
3. 同优先级按配置文件顺序选择。
4. 用户手动选择不可用 Provider 时直接报错。
5. 仅连接建立失败、明确 429 或 5xx 时允许切换一次候选 Provider。
6. 已收到有效供应商响应后不得再次调用其他供应商。
7. 400、401、403、内容安全拒绝、非法 JSON、Schema 校验失败不自动降级。
8. 读取响应超时属于计费状态不明确，不自动调用第二个供应商。
9. Mock 只有在 `AI__MOCK_ENABLED=true` 时进入候选。
10. 真实供应商失败不得静默切换 Mock。

### 5.5 前端实现

- 保留 Umi Max，不迁移 Vite。
- 工作台路由固定为 `/flowchart/workbench`。
- 根路径跳转工作台。
- 使用 Zustand 管理文档、任务、Provider、历史快照和脏状态。
- 使用 `@xyflow/react` 实现画布。
- 使用 dagre 实现 TB/LR 自动布局。
- 使用 Mermaid 进行只读源码预览；预览内容只来自后端最近一次成功编译结果，不参与双向绑定。
- 模型选择器显示 `displayName`；`providerId` 只作为内部值，不作为用户可见名称。
- Provider 列表加载失败、默认 Provider 不健康或路由切换时，显示可关闭的黄色非阻塞通知：`当前默认供应商响应异常，正在尝试降级/路由`；通知不阻塞输入和画布编辑。
- 前端将 `provider_unavailable`、`PROVIDER_UNAVAILABLE` 统一映射为 `上游服务繁忙，请稍后重试`，不得直接显示技术错误码；网络或本地 Provider 配置提示只能显示为“请检查网络连接或服务端配置”，不得显示实际 Base URL。
- `applyLayout` 先将所有节点坐标限制在 `[-10000, 10000]`，再提交 React Flow 状态；等待节点完成渲染后调用 `fitView({ padding: 0.2, minZoom: 0.5, maxZoom: 1.5 })`，禁止在旧节点状态上提前调用。
- Zustand 历史使用成熟的 `zundo` temporal middleware 或等价现有实现，`limit` 固定为 30；只记录可恢复的 `diagramData`，去重连续相同快照，不保存 Provider、SSE 和临时 UI 状态。
- SSE 使用 `fetch` 流式读取，以便安全携带认证请求头。
- `taskId`、`documentId` 使用应用命名空间保存到 `localStorage`。
- 不把供应商 Key、Base URL 或 `providerRequestId` 保存到前端。

### 5.6 数据库

V5 创建：

```text
flowchart_document
flowchart_task
flowchart_file
flowchart_template
flowchart_quota_log
flowchart_provider_call
flowchart_event
```

V6 写入系统内置模板。

规则：

- 主键使用 UUID v7。
- `user_id` 使用 `VARCHAR(64)`，兼容本地 UUID 和未来广场用户 ID。
- 不增加数据库外键，应用层保证一致性。
- `diagram_data` 使用 JSONB。
- `mermaid_source` 只保存后端最近一次成功编译结果；编译中的版本和失败原因写入 `flowchart_event.payload`，不把客户端 Mermaid 文本写入文档权威字段。
- Provider Key 和供应商完整请求正文不得入库。
- 已执行的 V1-V4 不得修改。

### 5.7 存储与导出

- MinIO 保存所有导出文件。
- 存储路径由服务端生成，客户端不能指定。
- 支持 SVG、PNG、Mermaid、JSON。
- 导出任务使用创建时的文档版本快照。
- 默认文件有效期 24 小时。
- 下载必须校验用户归属。
- 文件名移除路径分隔符、控制字符和系统保留名称。
- Chromium Worker 使用项目内 Inter 和 Source Han Sans SC 字体。
- 当前脚手架后端基于 `python:3.12-slim`（Debian），渲染 Worker 使用 Debian 安装方式：`apt-get install --no-install-recommends fontconfig fonts-dejavu-core`，复制 `fonts/Inter` 和 `fonts/SourceHanSansSC-Regular.otf` 到 `/usr/share/fonts/` 后执行 `fc-cache -fv`；只有明确切换到 Alpine 基础镜像时才使用 `apk add fontconfig ttf-dejavu`，禁止混用两套命令。
- Chromium 页面和浏览器上下文的单次渲染超时固定为 `30000ms`；超时必须关闭页面、上下文和浏览器进程，清理临时文件，并映射为 `EXPORT_RENDER_FAILED`。
- Mermaid 使用严格安全模式，禁止 HTML 和脚本执行。

### 5.8 本地部署

新增完整本地 Compose，包含：

```text
frontend
backend-api
celery-worker
celery-beat
postgres
redis
minio
```

本地固定端口：

```text
前端: 20105
后端: 10105
PostgreSQL: 5432
Redis: 6379
MinIO API: 9000
MinIO Console: 9001
```

目标启动命令：

```powershell
docker compose -f docker-compose.local.yml up -d --build
```

本地 Compose 使用项目内部网络，不依赖预先存在的 `infra-net`。

### 5.9 广场接入边界

本轮只定义并保留：

```text
IdentityProvider
QuotaPort
UsageReporter
```

本地默认：

- 使用现有 admin Bearer 登录。
- `QuotaPort` 返回无限额。
- 任务 `costPoints=0`。
- `UsageReporter` 为空实现。
- 不发送任何广场网络请求。

## 六、测试与验收

### 6.1 后端单元测试

必须覆盖：

- DiagramDocument 全部校验边界。
- Mermaid 类型映射与安全转义。
- 三种 Provider 协议的请求映射。
- 三种 Provider 协议的响应解析。
- Provider 配置校验和路由，包括 `displayName` 与 `model` 一致性校验。
- `provider_unavailable`、`PROVIDER_UNAVAILABLE` 到友好中文提示的统一映射。
- 401、403、429、5xx、超时、空结果、非法 JSON。
- 任务状态机、幂等、取消和重试。
- 节点坐标边界、`fitView` 参数和 30 条历史快照上限。
- 文档版本冲突。
- Mermaid 异步编译成功、失败和已保存 `diagramData` 保留。
- 文件路径、格式、MIME 和用户归属。

### 6.2 HTTP 契约测试

使用 `httpx` Mock Transport，不访问真实网络，覆盖：

- DeepSeek Chat Completions 的 `/chat/completions` 路径、Bearer 鉴权、`deepseek-v4-flash`、JSON 模式和 `finish_reason` 处理。
- DeepSeek Responses 的 `/responses` 路径、Bearer 鉴权、`deepseek-v4-flash`、`text.format`、`output_text` 和无状态参数约束。
- Anthropic Messages。
- OpenAI Chat Completions。
- OpenAI Responses。
- OpenAI-compatible 中转站。
- 原生结构化输出。
- JSON 提示词兜底。
- Markdown 包裹 JSON。
- 日志脱敏和供应商错误映射。

### 6.3 集成测试

在真实 PostgreSQL、Redis、MinIO、Celery 环境验证：

- V1-V6 升级。
- 任务入队和 Worker 执行。
- Redis 事件和 SSE。
- 任务刷新恢复。
- 文档保存和版本冲突。
- Mermaid 异步编译失败时文档 `diagramData` 仍可查询，`flowchart_event.payload` 返回脱敏失败状态。
- 四类导出。
- Chromium 中文字体加载、中文 glyph 渲染和 30 秒超时后的进程清理。
- 文件鉴权和过期清理。
- Worker 或 Beat 重启后的任务补偿。

### 6.4 前端和浏览器验收

验证：

- admin 登录。
- 描述输入和模板填充。
- Provider、模型选择；同名模型只展示一个选项，页面不显示 `providerId`。
- Provider 加载失败时黄色非阻塞通知、降级/路由提示和 `provider_unavailable` 友好文案。
- 创建、取消和重试任务。
- SSE 断开后的轮询。
- 刷新后恢复任务和文档。
- 节点新增、删除、复制、拖拽。
- 连线新增、删除和编辑。
- TB/LR 自动布局。
- 极端节点坐标被限制在 `[-10000, 10000]`，布局完成后 `fitView` 不超出 `0.5-1.5` 缩放范围。
- 撤销、重做和未保存提示；连续编辑超过 30 次后历史仍只保留最近 30 个快照。
- Mermaid 只读预览、编译中状态和编译失败状态；前端不能反向覆盖源码。
- 四类导出和下载。
- 桌面和移动视口无重叠、无文本溢出。

### 6.5 真实供应商验收

D15 在用户提供的未跟踪本地配置下执行：

1. DeepSeek Chat Completions 使用 `deepseek-v4-flash` 完成真实短请求。
2. DeepSeek Responses 使用 `deepseek-v4-flash` 完成真实短请求。
3. DeepSeek 官方 API 完成完整流程图生成链路。
4. Anthropic、OpenAI Chat、OpenAI Responses 和第三方中转站只执行 Mock 契约测试，不要求本轮提供真实凭据或完成真实联调。

要求：

- 不发送敏感业务数据。
- 限制最大输出 Token。
- 不记录 Key、完整提示词或完整供应商响应。
- 每条请求必须生成合法 DiagramDocument。
- 若 DeepSeek 凭据、额度或服务不可用，必须如实记录真实验收未完成，不得用 Mock 冒充。

### 6.6 性能验收

- 创建任务接口 1 秒内返回 `taskId` 或明确错误。
- 点击生成后 1 秒内显示任务状态。
- 50 节点、100 连线内可以正常操作。
- 50 节点、100 连线的大文档连续编辑不因历史快照无限增长而导致浏览器内存持续上升。
- 不出现忙轮询。
- SSE 不可用时固定每 2 秒查询本地任务。
- Provider 总超时默认 600 秒，可由配置覆盖。
- Chromium 单次渲染超时固定 30 秒，超时后不残留浏览器进程或临时文件。
- 任务进度不倒退。
- 刷新和重试不产生重复任务或重复供应商调用。

### 6.7 安全验收

- 用户只能访问自己的任务、文档和文件。
- API Key、Token、密码、Base URL 私有参数不出现在前端、响应或普通日志。
- Provider 配置只能由服务端加载。
- 模型输出只作为 JSON 数据处理。
- Mermaid 不执行 HTML 或脚本。
- 下载必须鉴权。
- 外部结果 URL 默认不接受；未来启用时必须配置域名白名单。
- `.env.local`、`providers.local.json` 和真实响应文件不得进入 Git。

## 七、明确不纳入本轮

- AI 应用广场真实 iframe 嵌入和联调。
- 广场临时 Token 签发与验证。
- HMAC 用量上报和真实积分扣费。
- Provider 管理后台和数据库动态配置。
- API Key 在线新增、修改和轮换。
- 供应商原生异步任务的真实 `poll`、`cancel`。
- 复杂熔断、成本路由和多级自动降级。
- 最近文档的完整管理页面。
- 个人模板和模板市场。
- 局部重新生成。
- Mermaid 反向解析。
- BPMN、UML、泳道图和时序图。
- 多人协作、评论和版本对比。
- 组织、运营和成本分析后台。
- 删除现有商品 CRUD、权限演示代码和历史迁移。
- `test` 到 `master` 的正式发布流程。

## 八、假设与默认值

- 当前 `test` 是唯一开发基线。
- 每日 MR 在下一日开始前完成审核并合入 `test`。
- 每个需求完成后允许自动提交和推送每日功能分支。
- 合入 `test` 仍需要用户单独确认。
- 用户不会在聊天中发送任何 API Key。
- 当前真实生成固定使用 DeepSeek 官方 API，默认模型为 `deepseek-v4-flash`，模型值保持可配置。
- DeepSeek 凭据由用户自行写入未跟踪的本地配置，环境变量名为 `DEEPSEEK_API_KEY`；Codex 不读取或回显其值。
- Anthropic、OpenAI 和中转站适配能力继续实现，但本轮不要求配置真实凭据或完成真实调用。
- 后续实施真实 OpenAI 调用前，需要单独确认复用现有 Key 还是创建新 Key。
- 第三方中转站遵循标准 Bearer 鉴权和 OpenAI Chat、Responses 响应结构。
- 中转站需要特殊请求头或私有协议时，不在本轮通用适配范围内。
- 本轮使用 `httpx`，不引入 OpenAI 或 Anthropic 官方 SDK。
- 本地 Mock 只用于自动测试和离线开发。
- 本地额度无限，生成成本记录为 0。
- 文档默认保存 30 天，任务记录默认保留 7 天，导出文件默认保留 24 小时。
