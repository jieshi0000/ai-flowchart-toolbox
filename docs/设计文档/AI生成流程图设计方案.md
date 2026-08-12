# AI 生成流程图 — 设计方案

**版本：** V1.0  
**状态：** 初稿  
**实现原则：** 不绑定任何单一大模型供应商；模型 API 统一经由 Provider Gateway 调用。优先复用 OpenAI 兼容协议，非兼容服务通过原生适配器接入。所有可能受模型时延影响的操作均以本地异步任务执行，前端只查询本系统任务状态。

---

## 一、技术选型

### 后端

| 技术 | 用途 | 对应模块 |
|------|------|----------|
| Python 3.12.10 + uv 0.11.28 | 本机已安装的运行时与项目环境管理 | 后端服务、Worker、流程图处理 |
| uv 0.11.28 | 创建项目 .venv、锁定依赖、执行开发命令 | 后端开发与测试 |
| FastAPI | HTTP API 框架 | 全部后端接口、SSE 任务事件 |
| Pydantic v2.13.4 | 请求校验、DiagramDocument 结构校验 | 接口、模型输出、文档保存 |
| SQLAlchemy 2.0 async + asyncpg | PostgreSQL ORM 与异步驱动 | 文档、任务、模板、日志 |
| PostgreSQL | 业务数据库 | 文档、任务、积分、模型调用日志 |
| Redis | Celery Broker、缓存、限流、短期任务状态 | 队列、SSE、频控 |
| Celery + Celery Beat | 可靠异步任务和定时补偿扫描 | 模型提交、供应商轮询、导出、清理 |
| httpx 0.28.1 | OpenAI 兼容和 REST API 调用 | Provider Gateway |
| jsonschema 4.26.0 | 严格验证模型返回 JSON | 流程图中间结构 |
| Mermaid CLI + Microsoft Edge 151 | 后端 Mermaid 转 SVG/PNG 的备用渲染能力；Edge 用作本机 Chromium 渲染内核 | 导出任务 |
| OSS / MinIO | 导出文件和临时结果存储 | SVG、PNG、Mermaid、JSON |

### 大模型供应商适配

系统不在业务代码中固定任何主模型或备用模型。供应商由服务端配置启用，模型路由只在启用且能力匹配的配置之间进行。

| 适配类型 | 适用范围 | 实现方式 |
|----------|----------|----------|
| OpenAICompatibleProvider | 提供 Chat Completions、Responses 或等价兼容协议的国内外服务 | 复用 httpx、统一 JSON Schema 提示词和响应转换 |
| NativeProvider | 使用非兼容 REST API 或官方 SDK 的服务 | 单独实现 submit、poll、cancel、health_check |
| SyncProvider | 请求在单次 HTTP 响应内返回完整结果的服务 | submit 后直接进入结果校验 |
| AsyncProvider | submit 返回供应商任务 ID，需后续查询结果的服务 | Worker 持久化任务 ID 并按退避策略轮询 |

可按用户后续提供的 API 信息接入 OpenAI、Azure OpenAI、Anthropic Claude、Google Gemini、DeepSeek、通义千问、豆包、智谱、月之暗面、MiniMax 或其他供应商。文档中的名称仅表示适配范围，不表示默认启用或已配置。

### 前端

| 技术 | 用途 | 对应模块 |
|------|------|----------|
| Node.js 20.19.0 + npm 10.8.2 | 本机前端运行时 | 前端构建、开发服务器 |
| pnpm 11.16.0 | 项目内依赖安装和脚本执行，不依赖全局 pnpm 包 | 前端工程 |
| React + TypeScript | 前端框架 | 全部 |
| Vite | 本地开发服务器、构建与环境变量注入 | 前端工程 |
| Ant Design | 表单、按钮、弹窗、消息、进度条和基础布局 | 全部 |
| React Router | 页面路由与工作台入口 | 应用工作台 |
| Zustand | 状态管理 | 文档、画布、任务、模型列表 |
| React Flow（@xyflow/react） | 节点、连线、拖拽、缩放、小地图和画布事件 | 流程图编辑器 |
| dagre | 有向流程图自动布局 | 从上到下、从左到右布局 |
| Mermaid | Mermaid 源码预览、复制和语义图渲染 | Mermaid 面板 |
| EventSource | 接收本系统 SSE 任务事件 | 任务状态同步 |

### 基础设施

| 技术 | 用途 |
|------|------|
| PostgreSQL | 业务数据持久化 |
| Redis | Celery Broker、限流、短期状态和事件广播 |
| MinIO / OSS | 导出文件存储 |
| Nginx | 前端静态资源、反向代理、SSE 代理、下载代理 |
| Docker 29.3.1 + Docker Compose v5.1.1 | 本机容器编排；启动服务前需先启动 Docker Desktop 引擎 |
| Microsoft Edge 151.0.4129.72 | 本机可用 Chromium 内核，供 Mermaid CLI 的受控渲染使用 |
| Inter + 思源黑体 Source Han Sans SC | 默认无衬线组合：英文与数字使用 Inter，中文使用思源黑体；两者均以 SIL Open Font License 1.1 发布，前端预览与 Worker 导出共用同一版本 | 字体渲染与商业分发 |
| 结构化日志与指标 | 任务耗时、轮询次数、供应商状态、成本和错误追踪 |

### 本机环境适配（2026-08-10）

下表只记录本次已确认可直接使用的本机环境；其他原有技术路线保持不变，待后续按项目需要安装或通过容器提供。

| 类别 | 已确认环境 | 在本项目中的使用方式 |
|------|------------|----------------------|
| 操作系统 | Windows 11 x64、PowerShell 5.1 | 本地命令统一按 PowerShell 和 Windows 路径编写 |
| 后端运行时 | Python 3.12.10、uv 0.11.28 | 使用 uv 为本项目创建隔离 .venv，不依赖全局 Python 包是否齐全 |
| 前端运行时 | Node.js 20.19.0、npm 10.8.2、pnpm 11.16.0 | 使用 pnpm.cmd 在项目目录内安装和运行前端依赖；不使用 pnpm 全局安装命令 |
| 容器工具 | Docker 29.3.1、Docker Compose v5.1.1 | 继续使用 Docker Compose 提供本地服务依赖；开发前手动启动 Docker Desktop |
| 浏览器内核 | Microsoft Edge 151.0.4129.72 | Mermaid CLI 需要浏览器时优先复用现有 Edge，可通过 PUPPETEER_EXECUTABLE_PATH 指定 |

---

## 二、项目结构

~~~text
ai-flowchart/
├── backend/
│   ├── src/app/
│   │   ├── api/
│   │   │   ├── provider.py             # 已启用模型公开信息与健康状态
│   │   │   ├── task.py                 # 任务创建、查询、取消、重试、SSE
│   │   │   ├── document.py             # 流程图文档查询与保存
│   │   │   ├── export.py               # 导出与下载
│   │   │   └── plaza.py                # 广场 Token 与用量上报
│   │   ├── models/
│   │   │   ├── base.py
│   │   │   ├── document.py             # flowchart_document
│   │   │   ├── task.py                 # flowchart_task
│   │   │   ├── file.py                 # flowchart_file
│   │   │   ├── template.py             # flowchart_template
│   │   │   ├── quota.py                # flowchart_quota_log
│   │   │   ├── provider_call.py        # flowchart_provider_call
│   │   │   └── event.py                # flowchart_event
│   │   ├── schemas/
│   │   │   ├── common.py               # Result、分页、错误结构
│   │   │   ├── diagram.py              # DiagramDocument、Node、Edge
│   │   │   ├── task.py                 # 任务请求与响应
│   │   │   ├── provider.py             # 供应商公开配置
│   │   │   ├── document.py             # 文档保存请求
│   │   │   └── export.py               # 导出请求
│   │   ├── services/
│   │   │   ├── diagram_service.py      # JSON 中间结构、Mermaid 编译、图校验
│   │   │   ├── task_engine.py          # 本地任务编排和状态机
│   │   │   ├── provider_router.py      # 供应商能力匹配、优先级与降级
│   │   │   ├── document_service.py     # 文档读取、保存、版本控制
│   │   │   ├── export_service.py       # SVG、PNG、Mermaid、JSON 导出
│   │   │   ├── quota_service.py        # 冻结、确认扣减、退款
│   │   │   ├── file_manager.py         # 对象存储、下载签名、清理
│   │   │   ├── event_service.py        # SSE 和埋点
│   │   │   └── cleanup_service.py      # 到期文档、文件和任务清理
│   │   ├── providers/
│   │   │   ├── base.py                 # Provider 协议和统一结果
│   │   │   ├── openai_compatible.py   # 通用兼容协议适配器
│   │   │   ├── native_base.py          # 原生 API 适配器基类
│   │   │   ├── provider_registry.py    # 服务端启用配置注册表
│   │   │   └── adapters/               # 后续按 API 需要新增的原生适配器
│   │   ├── workers/
│   │   │   ├── celery_app.py           # Celery 与 Redis 配置
│   │   │   ├── generate_worker.py      # 供应商 submit
│   │   │   ├── poll_worker.py          # 供应商 poll 与退避调度
│   │   │   ├── export_worker.py        # 导出任务
│   │   │   └── cleanup_worker.py       # 定时清理与漏轮询补偿
│   │   ├── config.py
│   │   ├── database.py
│   │   ├── exceptions.py
│   │   ├── logging_config.py
│   │   └── main.py
│   ├── tests/
│   │   ├── providers/
│   │   ├── services/
│   │   ├── api/
│   │   └── e2e/
│   └── pyproject.toml
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   └── flowchart.ts            # 流程图 API 封装
│   │   ├── stores/
│   │   │   └── flowchart.ts            # Zustand 文档、画布、任务、模型状态
│   │   ├── pages/flowchart/
│   │   │   ├── index.tsx               # 单页面工作台
│   │   │   └── components/
│   │   │       ├── PromptPanel.tsx
│   │   │       ├── TemplatePanel.tsx
│   │   │       ├── DiagramCanvas.tsx
│   │   │       ├── NodePropertyPanel.tsx
│   │   │       ├── MermaidPanel.tsx
│   │   │       ├── ExportPanel.tsx
│   │   │       └── TaskStatusBar.tsx
│   │   ├── routes/
│   │   │   └── index.tsx               # /flowchart/workbench 路由
│   │   └── main.tsx
│   ├── vite.config.ts
│   └── package.json
├── db/
│   └── V1__init_ai_flowchart.sql
├── docs/
│   ├── AI生成流程图需求文档.md
│   └── AI生成流程图设计方案.md
├── prototype/
│   ├── test_diagram_schema.py
│   ├── test_openai_compatible_provider.py
│   ├── test_async_provider_poll.py
│   ├── test_mermaid_render.py
│   └── test_reactflow_layout.ts
└── docker-compose.yml
~~~

---

## 三、与广场集成设计

### 3.1 iframe 通信流程

~~~text
AI 应用广场                              AI 生成流程图
─────                                    ────────────
1. 用户点击“立即使用”
2. GET /api/authorize?appId=ai-flowchart
3. 获取临时 Token
4. 渲染 iframe，src = appHomeUrl
                                        5. iframe 加载完成，发送 ready
    ◄─────────────────────────────────   postMessage({ type: "ready" })
6. 收到 ready，下发认证信息
7. postMessage({
     type: "AUTH_TOKEN",
     token: "Sa-Token",
     "X-User-Token": "临时Token",
     appId: "ai-flowchart"
   })
   ───────────────────────────────────► 8. 校验 origin 并接收 AUTH_TOKEN
                                        9. 使用命名空间保存 Token
                                       10. 后续请求携带 X-User-Token
~~~

### 3.2 前端实现要点

1. iframe 加载完成后向允许的父窗口 origin 发送 ready。
2. 监听 message 事件时必须校验 event.origin 和消息结构。
3. Token 使用应用命名空间保存，避免与广场其他子应用冲突。
4. 请求拦截器自动携带 X-User-Token。
5. 前端不处理 HMAC 签名、积分扣费、供应商 Key 或供应商任务 ID。
6. SSE 断开时自动退回本系统任务轮询，不直接请求第三方 API。

### 3.3 后端实现要点

1. 从请求头读取 X-User-Token 并解析用户身份和应用权限。
2. 文档、任务、导出文件均以 user_id 做强制归属校验。
3. 任务成功后向广场上报用量；上报使用独立幂等键。
4. 后端用 app_secret 生成 HMAC-SHA256 签名。
5. 供应商 API Key、Base URL、模型私有配置仅存在服务端环境变量或密钥管理系统。

### 3.4 用量上报

~~~json
{
  "appId": "ai-flowchart",
  "userId": "xxx",
  "taskId": "xxx",
  "toolType": "diagram_generate",
  "usage": 1,
  "costPoints": 1,
  "provider": "provider_x",
  "model": "model_y",
  "durationMs": 38200
}
~~~

仅当模型返回有效结果、DiagramDocument 校验通过、文档持久化成功后才确认扣费。失败、取消、超时和结构校验失败统一走退款或不扣费路径。

---

## 四、页面架构

### 4.1 布局

~~~text
┌─────────────────────────────────────────────────────────────────────┐
│ 顶部栏：Logo / AI 生成流程图 / 模型状态 / 积分余额 / 文件安全说明       │
├─────────────────────────────────────────────────────────────────────┤
│ 工具栏：生成 | 编辑 | Mermaid | 导出                                  │
├───────────────┬─────────────────────────────────┬───────────────────┤
│ 左侧输入区     │ 中间流程图画布                    │ 右侧属性面板       │
│ - 描述输入     │ - React Flow 节点与连线            │ - 节点属性         │
│ - 方向与粒度   │ - 缩放 / 小地图 / 自动布局          │ - 文档属性         │
│ - 模板         │ - 空状态 / 加载状态                 │ - Mermaid / 导出   │
│ - 最近任务     │                                    │                   │
├───────────────┴─────────────────────────────────┴───────────────────┤
│ 底部状态栏：本地任务阶段 / 进度 / 轮询提示 / 取消 / 重试 / 下载结果     │
└─────────────────────────────────────────────────────────────────────┘
~~~

### 4.2 组件树

~~~text
pages/flowchart/index.tsx
├── 顶部应用信息区
├── FlowchartToolTabs
├── PromptPanel
│   ├── PromptEditor
│   ├── GenerateOptions
│   ├── ProviderSelector
│   ├── TemplatePanel
│   └── RecentTaskList
├── DiagramCanvas
│   ├── EmptyState
│   ├── CanvasToolbar
│   ├── ReactFlow
│   ├── Background
│   ├── MiniMap
│   └── Controls
├── RightPanel
│   ├── NodePropertyPanel
│   ├── DocumentPropertyPanel
│   ├── MermaidPanel
│   └── ExportPanel
└── TaskStatusBar
~~~

### 4.3 状态管理

Zustand store 为 flowchart.ts。DiagramDocument 保存业务语义和画布布局；Mermaid 源码由 DiagramDocument 派生，不能作为首期反向编辑的数据源。

~~~ts
type NodeType =
  | 'start'
  | 'end'
  | 'process'
  | 'decision'
  | 'input_output'
  | 'subprocess';

type LocalTaskStatus =
  | 'idle'
  | 'waiting'
  | 'submitting'
  | 'provider_queued'
  | 'provider_processing'
  | 'validating'
  | 'rendering'
  | 'success'
  | 'failed'
  | 'canceled'
  | 'expired';

interface DiagramNode {
  id: string;
  type: NodeType;
  label: string;
  position: { x: number; y: number };
  style?: {
    fill?: string;
    stroke?: string;
  };
}

interface DiagramEdge {
  id: string;
  source: string;
  target: string;
  label?: string;
  condition?: string;
}

interface DiagramDocument {
  id: string;
  title: string;
  direction: 'TB' | 'LR';
  nodes: DiagramNode[];
  edges: DiagramEdge[];
  mermaidSource: string;
  metadata: {
    generatedBy?: string;
    model?: string;
    sourceTaskId?: string;
    version: number;
  };
}

interface TaskStatus {
  taskId: string | null;
  status: LocalTaskStatus;
  progress: number;
  stage: string;
  providerId: string | null;
  modelName: string | null;
  message: string;
  documentId: string | null;
  errorCode: string | null;
}
~~~

刷新恢复逻辑：

1. 页面加载时读取本地保存的 taskId 和 documentId。
2. 调用 GET /api/flowchart/tasks/{taskId} 查询本地任务。
3. 任务未结束时优先重新建立 SSE；连接失败时每 2 秒轮询本系统任务接口。
4. 任务成功时读取 documentId 并加载 DiagramDocument。
5. 任务失败时显示错误原因和重试按钮。
6. 页面关闭前，如存在未保存编辑或未结束任务，显示确认提示。

### 4.4 工具面板交互细则

#### 描述输入与生成

| 控件 | 交互规则 |
|------|----------|
| 描述输入框 | 多行输入，限制 1 至 4000 字符，支持示例一键填入 |
| 图方向 | 自上而下 TB 或从左到右 LR |
| 图粒度 | 简洁、标准、详细；影响 Prompt 中期望节点数量 |
| 模型选择 | 仅展示后端返回的 enabled 模型，默认自动路由 |
| 生成按钮 | 调用 POST /api/flowchart/tasks，立即返回 taskId |
| 取消按钮 | 仅在未结束任务显示，调用本地取消接口 |
| 重试按钮 | 失败任务沿用请求快照，生成新的本地 taskId |

#### 节点画布

| 控件 | 交互规则 |
|------|----------|
| 节点拖拽 | 仅更新 DiagramDocument 中的 position |
| 节点文本 | 双击或右侧面板修改 label，实时更新 Mermaid 语义 |
| 连线 | 通过 React Flow 创建或删除，校验 source 和 target 是否存在 |
| 节点类型 | 在右侧面板切换，更新画布外观与 Mermaid 节点语法 |
| 自动布局 | 调用 dagre 计算 position，保留节点业务 id 和连线 |
| 缩放与平移 | 使用 React Flow 内置 Controls 与 fitView |
| 撤销重做 | 使用本地命令栈，文档保存成功后重置脏状态 |

#### Mermaid 与导出

| 控件 | 交互规则 |
|------|----------|
| Mermaid 查看 | 只读显示由当前 DiagramDocument 编译的源码 |
| 复制源码 | 使用浏览器剪贴板 API，失败时显示可复制文本框 |
| SVG / PNG 导出 | 创建 export 任务，由后端按当前文档快照渲染 |
| Mermaid / JSON 导出 | 创建文件并保存到对象存储，返回下载入口 |
| 导出状态 | 在底部任务栏显示；导出不影响当前画布编辑 |

位置、颜色等画布表现保存到 JSON 中间结构。Mermaid 负责表达节点和连线语义，因此 Mermaid 自动布局与用户手工画布位置不要求像素级一致。

---

## 五、异步任务引擎

### 5.1 设计原则

- 所有模型生成、供应商轮询和服务端导出均创建本地任务。
- 普通 HTTP 请求只创建任务、保存参数和入队，不等待模型生成完成。
- 本地任务状态持久化到 PostgreSQL；Redis 仅承担队列、短期进度和事件广播。
- 前端通过 SSE 获取本地任务事件，轮询本地任务接口作为兜底。
- 供应商轮询仅在 Worker 内执行，浏览器不持有供应商任务 ID、API Key 或轮询地址。
- 任务支持取消、重试、刷新恢复、超时处理和漏轮询补偿。
- 供应商请求、积分操作和用量上报均使用幂等键。

### 5.2 处理流程

~~~text
前端               后端 API            Redis/Celery Worker          供应商 API / 存储
────               ────────            ───────────────────          ─────────────────
1. 输入描述
2. 点击生成
  ───────────────► 3. 校验参数、创建本地 task
                    4. 冻结积分、写请求快照、生成 idempotency_key
                    5. 发送队列消息
  ◄─────────────── 6. 返回 taskId

7. 建立 SSE / 本地轮询
                                      8. Worker 调用 provider.submit
                                                                        ───────────────►
                                      9. 保存 providerRequestId
                                     10. 若异步，按 next_poll_at 调度 poll
                                                                        ◄───────────────
                                     11. 下载或读取最终结果
                                     12. 校验 DiagramDocument
                                     13. 编译 Mermaid、保存文档
                                     14. 成功扣费并上报用量
  ◄─────────────── 15. SSE 推送 success / 前端加载文档
~~~

### 5.3 本地任务状态机

~~~text
  waiting
     │
     ▼
 submitting ────────────────► failed
     │
     ├── 同步结果 ───────────► validating ─► rendering ─► success
     │
     ▼
 provider_queued
     │
     ▼
 provider_processing
     │
     └──────────────────────► validating ─► rendering ─► success

canceled：可发生在 waiting、submitting、provider_queued、provider_processing
expired：到期清理后的历史终态
failed：参数错误、供应商终态错误、超时、结构校验失败或渲染失败
~~~

### 5.4 供应商任务协议

~~~python
class ProviderSubmission:
    provider_request_id: str | None
    mode: str                 # sync 或 async
    status: str               # queued、processing、succeeded、failed
    result: dict | None
    retry_after_seconds: int | None

class ProviderPollResult:
    status: str               # queued、processing、succeeded、failed、canceled
    result: dict | None
    progress: int | None
    retry_after_seconds: int | None
    error_code: str | None
    error_message: str | None

class ProviderResult:
    success: bool
    provider: str
    model: str
    request_id: str | None
    data: dict | None
    error_code: str | None
    error_message: str | None
    duration_ms: int
    cost_amount: float | None
~~~

### 5.5 轮询、重试与超时

| 场景 | 处理规则 |
|------|----------|
| 同步供应商返回成功 | 不创建实际轮询，直接进入 validating |
| 异步供应商提交成功 | 保存 provider_request_id，首次 poll 在 3 秒后运行 |
| 供应商返回 Retry-After | 使用该值，仍受服务端允许范围保护 |
| 正常处理中 | 按 3 秒、6 秒、12 秒、15 秒、15 秒的退避序列安排后续 poll |
| 网络错误、429、5xx | 记录 retry_count，使用带随机抖动的退避重试 |
| 参数错误、内容安全拒绝、余额不足 | 直接终止，不重试 |
| 总耗时超过 deadline_at | 尽力调用 provider.cancel，结束本地任务并退款 |
| Worker 重启或消息丢失 | Celery Beat 每分钟扫描 next_poll_at 已过期的未结束任务并补调度 |
| 供应商结果为临时 URL | Worker 立即拉取到对象存储，校验 MIME、大小和有效性 |

默认 provider 总超时为 600 秒，配置可按供应商和模型覆盖。轮询永远不能使用忙循环。

### 5.6 幂等、取消与降级

1. 创建本地任务时生成 idempotency_key，并在同一用户和同一请求窗口内去重。
2. 调用 provider.submit 时将 idempotency_key 传给支持该能力的供应商；不支持时以本地锁和请求日志避免重复提交。
3. 取消请求首先原子更新本地取消标志，再由 Worker 尽力调用 provider.cancel。
4. 已处于供应商处理中任务，不因单次网络超时自动切换到另一个供应商，避免重复生成和重复成本。
5. 自动降级只允许发生在未获得有效 provider_request_id 时，或供应商返回明确可重试终态失败且无计费结果时。
6. 用量上报以 task_id 作为幂等关联，不因 Worker 重试而重复扣费。

### 5.7 进度设计

| 阶段 | 默认进度 | 前端文案 |
|------|----------|----------|
| waiting | 5 | 任务已创建，等待处理 |
| submitting | 15 | 正在提交生成请求 |
| provider_queued | 25 | 模型服务正在排队 |
| provider_processing | 55 | 模型正在生成流程图 |
| validating | 75 | 正在校验流程图结构 |
| rendering | 90 | 正在生成 Mermaid 和导出结果 |
| success | 100 | 流程图已生成 |

供应商返回真实进度时，按阶段范围映射，不允许进度倒退。供应商不返回进度时显示阶段文案和等待时长。

---

## 六、模块详细设计

### 6.1 供应商注册、配置与路由

服务端 Provider Registry 从安全配置源加载公开的供应商档案。任何 Key、Secret、完整 Endpoint 凭据均不得写入业务表、前端响应或普通日志。

~~~json
{
  "providerId": "provider_x",
  "displayName": "已配置模型服务",
  "protocol": "openai-compatible",
  "model": "model-y",
  "capabilities": [
    "text_generation",
    "structured_output"
  ],
  "timeoutSeconds": 60,
  "pollIntervalSeconds": 3,
  "maxPollIntervalSeconds": 15,
  "taskTimeoutSeconds": 600,
  "enabled": true,
  "priority": 10
}
~~~

路由步骤：

1. 根据任务类型要求 structured_output 和 text_generation 能力。
2. 过滤 disabled、健康检查失败或当前限流的供应商。
3. 用户选择模型时，仅在其满足能力要求且已启用时使用。
4. 未指定模型时，按 priority、近期错误率和限流状态选择。
5. 记录实际 provider_id、model_name、protocol 和选择原因。
6. 当可安全降级时，记录 fallback_reason 和前后供应商。

### 6.2 Prompt 处理与 DiagramDocument

模型输出不作为自由 HTML、脚本或可执行代码处理。后端将用户输入包装为固定系统提示词，要求仅返回符合 JSON Schema 的流程图数据。

~~~json
{
  "title": "请假审批流程",
  "direction": "TB",
  "nodes": [
    {
      "id": "start",
      "type": "start",
      "label": "员工提交请假申请",
      "position": { "x": 0, "y": 0 }
    },
    {
      "id": "check",
      "type": "decision",
      "label": "主管是否批准",
      "position": { "x": 0, "y": 120 }
    },
    {
      "id": "end",
      "type": "end",
      "label": "流程结束",
      "position": { "x": 0, "y": 240 }
    }
  ],
  "edges": [
    {
      "id": "e1",
      "source": "start",
      "target": "check"
    },
    {
      "id": "e2",
      "source": "check",
      "target": "end",
      "label": "是"
    }
  ]
}
~~~

校验规则：

- title、节点 id、标签和边标签长度符合限制。
- 节点 id 在单一文档中唯一。
- 边的 source 和 target 必须指向存在节点。
- 节点 type 仅允许首期定义的六种类型。
- 单张图最多 50 个节点、100 条边。
- 标签会转义 Mermaid 特殊字符和 HTML，不允许脚本、事件属性或原始 HTML。
- 允许合法循环边；孤立节点和缺少开始或结束节点作为可编辑警告，不强制拒绝生成。

### 6.3 Mermaid 编译

DiagramDocument 到 Mermaid 的转换由后端服务统一完成，避免让模型直接输出未验证 Mermaid。

~~~text
DiagramDocument JSON
  → 节点类型映射
  → 标签转义
  → 连线和判断条件映射
  → flowchart TB 或 flowchart LR
  → Mermaid 源码
~~~

节点映射：

| DiagramNode.type | Mermaid 表达 |
|------------------|-------------|
| start / end | 圆角节点 |
| process | 矩形节点 |
| decision | 菱形节点 |
| input_output | 平行四边形节点 |
| subprocess | 双边框子流程节点 |

Mermaid 源码用于查看、复制和语义导出。画布手动位置、颜色和尺寸保留在 diagram_data 中，不要求 Mermaid 自动布局复现像素级位置。

### 6.4 节点画布与自动布局

| 项目 | 实现 | 技术栈 |
|------|------|--------|
| 节点和连线渲染 | React Flow 受控 nodes / edges | React Flow |
| 拖拽与缩放 | 直接更新 position 和视图状态 | React Flow |
| 节点形状 | 自定义节点组件映射六种 NodeType | React 组件 |
| 自动布局 | 将节点和边转换为 dagre 图，再回写 position | dagre |
| 校验提示 | 服务端保存校验 + 前端实时轻量校验 | TypeScript + Pydantic |
| 撤销重做 | 命令栈保存 DiagramDocument 快照 | Zustand |

画布保存采用乐观锁：

1. 前端请求携带 document.version。
2. 后端仅在版本一致时写入 diagram_data 和 mermaid_source。
3. 版本冲突时返回最新文档，提示用户重新加载；首期不实现多人协作合并。

### 6.5 文档、模板与历史

| 项目 | 实现 | 技术栈 |
|------|------|--------|
| 文档保存 | DiagramDocument JSONB、Mermaid 源码、版本号 | PostgreSQL |
| 内置模板 | user_id 为空的系统模板 | PostgreSQL |
| 个人模板 | user_id 为当前用户，保存当前 diagram_data | PostgreSQL |
| 最近任务 | 按 user_id、created_at 查询成功和失败任务 | PostgreSQL |
| 结果恢复 | task 成功后通过 document_id 加载完整文档 | PostgreSQL |

### 6.6 导出与文件管理

| 格式 | 实现 |
|------|------|
| Mermaid | 保存由 DiagramDocument 编译的 .mmd 文本 |
| JSON | 保存当前 DiagramDocument JSON 快照 |
| SVG | 优先使用 Mermaid CLI 或受控渲染组件生成矢量文件 |
| PNG | 在服务器渲染 SVG 后转换 PNG，避免浏览器跨域资源污染 |

### 6.6.1 Mermaid 渲染环境分层

~~~text
本机开发：复用 Edge
正式部署：Worker 镜像内安装 Chromium（推荐）
高并发后期：拆出独立流程图渲染 Worker 或渲染服务
~~~

Mermaid CLI 仅由导出 Worker 调用；正式环境不依赖宿主机安装 Edge、Chrome 或其他浏览器。

### 6.6.2 字体与商业授权策略

默认无衬线组合固定为 Inter 与思源黑体 Source Han Sans SC：英文和数字优先使用 Inter，中文字符回退到思源黑体。两者均以 SIL Open Font License 1.1 发布；首期不使用 Windows 宋体 SimSun、Times New Roman 或其他宿主机字体作为默认或兜底字体，避免部署镜像、Linux Worker 与 Windows 本机之间出现授权和字形不一致。

~~~text
前端 Mermaid.js / React Flow
  └── @font-face 加载项目内 Inter 与 Source Han Sans SC 字体文件

导出 Worker / Mermaid CLI
  └── Worker 镜像复制同版本字体文件
  └── 执行 fc-cache 后由 Chromium 使用 Inter 与 Source Han Sans SC

SVG / PNG
  └── 渲染前确认字体就绪，确保与前端预览使用相同字体族
~~~

实现规则：

1. 项目维护字体白名单，首期仅开放 Inter 与 Source Han Sans SC 的常规和粗体字重。
2. 前端通过 @font-face 引用项目内字体，调用 Mermaid.js 渲染或截图前等待 document.fonts.ready。
3. Worker 镜像将相同字体文件复制到标准字体目录并刷新 fontconfig 缓存；导出前可通过 fc-match 检查字体是否可用。
4. Mermaid 配置与前端节点样式统一指定 fontFamily 为 Inter、Source Han Sans SC、sans-serif，使英文与数字优先使用 Inter，中文回退到思源黑体。
5. 字体文件旁保留对应 OFL 许可证、版本和来源说明；新增字体必须先确认可免费商用和可随镜像再分发。
6. 首期不提供用户上传字体或任意系统字体选择，以避免无法验证的授权和导出环境不一致。

导出任务使用当前 document.version 的快照，避免导出时用户继续编辑导致结果不确定。Worker 将结果写入对象存储，生成 flowchart_file 记录，并返回短期鉴权下载链接。

### 6.7 模型结果安全处理

1. 提示词和模型输出均按数据处理，禁止作为模板代码或脚本执行。
2. 供应商返回 Markdown、思维过程或额外文本时，适配器只提取可验证 JSON；无法提取则标记结构校验失败。
3. Mermaid 预览使用严格安全配置，关闭 HTML 标签和 JavaScript 执行能力。
4. 外部结果 URL 仅允许 Worker 访问经配置的可信域名，并校验重定向、MIME、大小和超时。
5. 结构化日志仅记录任务 ID、供应商 ID、模型名、耗时和错误码，不记录 API Key 或完整用户敏感描述。

---

## 七、接口详细设计

### 7.1 查询已启用供应商

~~~text
GET /api/flowchart/providers

响应：
{
  "code": 200,
  "data": [
    {
      "providerId": "provider_x",
      "displayName": "已配置模型服务",
      "model": "model-y",
      "capabilities": ["text_generation", "structured_output"],
      "status": "healthy",
      "allowManualSelection": true
    }
  ],
  "message": "success",
  "timestamp": 1783072800000
}
~~~

响应不得包含 API Key、baseUrl、供应商请求头、模型私有参数或健康检查原始错误。

### 7.2 创建流程图任务

~~~text
POST /api/flowchart/tasks
Content-Type: application/json

请求参数：
{
  "type": "diagram_generate",
  "prompt": "用户提交请假申请，主管审批，通过后通知员工，不通过则退回修改。",
  "direction": "TB",
  "detailLevel": "standard",
  "providerId": null,
  "model": null
}

响应：
{
  "code": 200,
  "data": {
    "taskId": "uuid",
    "status": "waiting",
    "estimatedSeconds": 30
  },
  "message": "success",
  "timestamp": 1783072800000
}
~~~

接口完成本地参数校验、用户权限校验、幂等检查、积分冻结和入队；不得等待模型完整响应。

### 7.3 查询任务

~~~text
GET /api/flowchart/tasks/{taskId}

响应：
{
  "code": 200,
  "data": {
    "taskId": "uuid",
    "type": "diagram_generate",
    "status": "provider_processing",
    "progress": 55,
    "stage": "模型正在生成流程图",
    "providerId": "provider_x",
    "modelName": "model-y",
    "pollCount": 3,
    "documentId": null,
    "downloadUrl": null,
    "errorCode": null,
    "errorMessage": null
  },
  "message": "success",
  "timestamp": 1783072800000
}
~~~

### 7.4 任务事件流

~~~text
GET /api/flowchart/tasks/{taskId}/events
Accept: text/event-stream

事件示例：
event: task-status
data: {
  "taskId": "uuid",
  "status": "validating",
  "progress": 75,
  "stage": "正在校验流程图结构"
}
~~~

SSE 只推送本地任务事件。客户端连接失败、网络代理不支持 SSE 或 30 秒未收到事件时，退回 GET /api/flowchart/tasks/{taskId} 轮询。

### 7.5 取消任务

~~~text
POST /api/flowchart/tasks/{taskId}/cancel

响应：
{
  "code": 200,
  "data": {
    "taskId": "uuid",
    "status": "canceled",
    "providerCancelRequested": true
  },
  "message": "success",
  "timestamp": 1783072800000
}
~~~

取消接口只保证本地任务不再向前推进；供应商取消为尽力而为，最终退款和状态收敛由 Worker 完成。

### 7.6 重试任务

~~~text
POST /api/flowchart/tasks/{taskId}/retry

响应：
{
  "code": 200,
  "data": {
    "taskId": "new-uuid",
    "sourceTaskId": "old-uuid",
    "status": "waiting"
  },
  "message": "success",
  "timestamp": 1783072800000
}
~~~

重试始终创建新任务，原任务保持终态，便于审计和避免幂等键冲突。

### 7.7 查询流程图文档

~~~text
GET /api/flowchart/documents/{documentId}

响应：
{
  "code": 200,
  "data": {
    "id": "uuid",
    "title": "请假审批流程",
    "direction": "TB",
    "nodes": [],
    "edges": [],
    "mermaidSource": "flowchart TB ...",
    "metadata": {
      "version": 1,
      "sourceTaskId": "uuid",
      "model": "model-y"
    }
  },
  "message": "success",
  "timestamp": 1783072800000
}
~~~

### 7.8 保存流程图文档

~~~text
POST /api/flowchart/documents/{documentId}/save
Content-Type: application/json

请求参数：
{
  "version": 1,
  "title": "请假审批流程",
  "direction": "TB",
  "nodes": [],
  "edges": []
}

响应：
{
  "code": 200,
  "data": {
    "documentId": "uuid",
    "version": 2,
    "mermaidSource": "flowchart TB ..."
  },
  "message": "success",
  "timestamp": 1783072800000
}
~~~

后端重新校验 JSON 中间结构并重新编译 Mermaid，不接受客户端直接覆盖 mermaidSource。

### 7.9 创建导出任务

~~~text
POST /api/flowchart/documents/{documentId}/export
Content-Type: application/json

请求参数：
{
  "format": "SVG",
  "background": "transparent"
}

响应：
{
  "code": 200,
  "data": {
    "taskId": "uuid",
    "status": "waiting"
  },
  "message": "success",
  "timestamp": 1783072800000
}
~~~

format 仅允许 SVG、PNG、MERMAID、JSON。

### 7.10 下载导出文件

~~~text
GET /api/flowchart/files/download?fileId=uuid

响应：
文件二进制流或短期签名 URL
Content-Disposition: attachment; filename="请假审批流程.svg"
~~~

---

## 八、数据库设计

### 8.1 DDL（V1__init_ai_flowchart.sql）

~~~sql
CREATE TABLE flowchart_document (
    id              UUID PRIMARY KEY,
    user_id         VARCHAR(64) NOT NULL,
    title           VARCHAR(100) NOT NULL,
    direction       VARCHAR(4) NOT NULL DEFAULT 'TB',
    diagram_data    JSONB NOT NULL,
    mermaid_source  TEXT NOT NULL,
    version         INTEGER NOT NULL DEFAULT 1,
    source_task_id  UUID,
    expires_at      TIMESTAMP NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE flowchart_task (
    id                  UUID PRIMARY KEY,
    user_id             VARCHAR(64) NOT NULL,
    type                VARCHAR(40) NOT NULL,
    status              VARCHAR(32) NOT NULL DEFAULT 'waiting',
    progress            INTEGER NOT NULL DEFAULT 0,
    stage               VARCHAR(80),
    request_snapshot    JSONB NOT NULL,
    result              JSONB,
    document_id         UUID,
    output_file_id      UUID,
    provider_id         VARCHAR(80),
    model_name          VARCHAR(160),
    provider_request_id VARCHAR(255),
    provider_status     VARCHAR(40),
    idempotency_key     VARCHAR(128) NOT NULL,
    poll_count          INTEGER NOT NULL DEFAULT 0,
    retry_count         INTEGER NOT NULL DEFAULT 0,
    next_poll_at        TIMESTAMP,
    deadline_at         TIMESTAMP,
    last_provider_error TEXT,
    usage_report_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    queue_wait_ms       INTEGER,
    provider_wait_ms    INTEGER,
    render_duration_ms  INTEGER,
    error_code          VARCHAR(100),
    error_message       TEXT,
    cost_points         INTEGER NOT NULL DEFAULT 0,
    expires_at          TIMESTAMP NOT NULL,
    created_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMP NOT NULL DEFAULT NOW(),
    CONSTRAINT uq_flowchart_task_idempotency UNIQUE (user_id, idempotency_key)
);

CREATE TABLE flowchart_file (
    id              UUID PRIMARY KEY,
    user_id         VARCHAR(64) NOT NULL,
    document_id     UUID,
    task_id         UUID,
    original_name   VARCHAR(255) NOT NULL,
    stored_path     VARCHAR(500) NOT NULL,
    file_size       BIGINT NOT NULL,
    mime_type       VARCHAR(80) NOT NULL,
    format          VARCHAR(20) NOT NULL,
    file_role       VARCHAR(40) NOT NULL,
    expires_at      TIMESTAMP NOT NULL,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE flowchart_template (
    id              UUID PRIMARY KEY,
    user_id         VARCHAR(64),
    type            VARCHAR(40) NOT NULL,
    category        VARCHAR(80) NOT NULL,
    name            VARCHAR(120) NOT NULL,
    description     TEXT,
    config          JSONB NOT NULL,
    sort_order      INTEGER NOT NULL DEFAULT 0,
    enabled         BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE flowchart_quota_log (
    id              UUID PRIMARY KEY,
    user_id         VARCHAR(64) NOT NULL,
    task_id         UUID,
    action          VARCHAR(20) NOT NULL,
    points          INTEGER NOT NULL,
    balance_before  INTEGER,
    balance_after   INTEGER,
    reason          VARCHAR(255),
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE flowchart_provider_call (
    id              UUID PRIMARY KEY,
    task_id         UUID NOT NULL,
    user_id         VARCHAR(64) NOT NULL,
    provider_id     VARCHAR(80) NOT NULL,
    model_name      VARCHAR(160) NOT NULL,
    protocol        VARCHAR(40) NOT NULL,
    request_id      VARCHAR(255),
    operation       VARCHAR(20) NOT NULL,
    status          VARCHAR(20) NOT NULL,
    duration_ms     INTEGER,
    poll_count      INTEGER NOT NULL DEFAULT 0,
    retry_count     INTEGER NOT NULL DEFAULT 0,
    fallback_reason VARCHAR(255),
    cost_amount     NUMERIC(12, 6),
    error_code      VARCHAR(120),
    error_message   TEXT,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE TABLE flowchart_event (
    id              UUID PRIMARY KEY,
    user_id         VARCHAR(64),
    event_name      VARCHAR(80) NOT NULL,
    task_id         UUID,
    document_id     UUID,
    payload         JSONB,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE flowchart_document IS '流程图文档表，diagram_data 为唯一权威的 JSON 中间结构';
COMMENT ON TABLE flowchart_task IS '异步任务表，记录模型提交、供应商轮询、校验、渲染和导出任务';
COMMENT ON TABLE flowchart_file IS '导出文件表，保存 SVG、PNG、Mermaid、JSON 的对象存储路径';
COMMENT ON TABLE flowchart_template IS '流程图模板表，user_id 为空时表示系统模板';
COMMENT ON TABLE flowchart_quota_log IS '积分流水表，记录冻结、确认扣减和退款';
COMMENT ON TABLE flowchart_provider_call IS '模型调用日志表，不保存 API Key 或请求密文';
COMMENT ON TABLE flowchart_event IS '埋点事件表，记录生成、编辑、导出和下载行为';
~~~

### 8.2 索引

~~~sql
CREATE INDEX idx_flowchart_document_user_id
    ON flowchart_document(user_id);
CREATE INDEX idx_flowchart_document_expires_at
    ON flowchart_document(expires_at);

CREATE INDEX idx_flowchart_task_user_id
    ON flowchart_task(user_id);
CREATE INDEX idx_flowchart_task_status
    ON flowchart_task(status);
CREATE INDEX idx_flowchart_task_document_id
    ON flowchart_task(document_id);
CREATE INDEX idx_flowchart_task_next_poll_at
    ON flowchart_task(next_poll_at)
    WHERE status IN ('provider_queued', 'provider_processing');
CREATE INDEX idx_flowchart_task_deadline_at
    ON flowchart_task(deadline_at)
    WHERE status IN ('waiting', 'submitting', 'provider_queued', 'provider_processing');

CREATE INDEX idx_flowchart_file_user_id
    ON flowchart_file(user_id);
CREATE INDEX idx_flowchart_file_expires_at
    ON flowchart_file(expires_at);

CREATE INDEX idx_flowchart_template_user_category
    ON flowchart_template(user_id, category);
CREATE INDEX idx_flowchart_provider_call_task_id
    ON flowchart_provider_call(task_id);
CREATE INDEX idx_flowchart_provider_call_provider_model
    ON flowchart_provider_call(provider_id, model_name);
CREATE INDEX idx_flowchart_event_name
    ON flowchart_event(event_name);
~~~

### 8.3 数据清理

| 数据 | 默认有效期 | 清理策略 |
|------|------------|----------|
| 导出文件 | 24 小时 | 定时删除对象存储对象和 flowchart_file 记录 |
| 任务记录 | 7 天 | 到期后清理非必要请求快照和临时结果 |
| 流程图文档 | 30 天 | 到期前提示导出或续存，按策略删除 |
| 模型调用日志 | 90 天 | 保留用于成本、轮询和故障统计 |
| 埋点事件 | 180 天 | 用于运营分析 |

---

## 九、异常码规范

### 9.1 原则

- 业务异常 HTTP 统一返回 200，Result.code 表示业务状态；未捕获异常使用 HTTP 500。
- 供应商原始错误必须映射为用户可理解的中文文案。
- 响应和日志不暴露 API Key、请求签名、完整供应商请求体或内部堆栈。
- 前端可依据 errorCode 决定是否展示重试、取消或重新编辑描述入口。

### 9.2 错误码

| code | 含义 | 触发场景 |
|------|------|----------|
| 200 | 成功 | — |
| 400 | 参数错误 | 描述、格式、节点或导出参数不合法 |
| 401 | 未认证 | Token 缺失或过期 |
| 403 | 无权限 | 访问非本人文档、任务或文件 |
| 404 | 资源不存在 | 文档、任务、文件或模型不存在 |
| 409 | 状态冲突 | 已结束任务取消、文档版本冲突 |
| 429 | 请求过快 | 用户频控、系统限流或供应商限流 |
| 500 | 服务端异常 | 内部处理失败 |
| 502 | 供应商服务异常 | 模型 API 返回错误 |
| 504 | 供应商服务超时 | 模型提交或轮询超时 |

### 9.3 业务错误码

| errorCode | 说明 |
|-----------|------|
| PROMPT_EMPTY | 流程描述为空 |
| PROMPT_TOO_LONG | 流程描述超过长度限制 |
| PROVIDER_NOT_CONFIGURED | 没有满足能力要求的已启用模型 |
| PROVIDER_UNHEALTHY | 指定模型当前不可用 |
| PROVIDER_RATE_LIMITED | 供应商限流 |
| PROVIDER_SUBMIT_FAILED | 供应商任务提交失败 |
| PROVIDER_POLL_FAILED | 供应商任务查询失败 |
| PROVIDER_TASK_TIMEOUT | 供应商任务超过 deadline_at |
| PROVIDER_CANCEL_FAILED | 供应商取消请求失败，已在本地收敛 |
| DIAGRAM_SCHEMA_INVALID | 模型返回不符合 DiagramDocument 结构 |
| DIAGRAM_NODE_LIMIT_EXCEEDED | 节点数量超过首期限额 |
| DIAGRAM_EDGE_INVALID | 连线引用不存在节点或格式无效 |
| MERMAID_RENDER_FAILED | Mermaid 编译或渲染失败 |
| EXPORT_FORMAT_UNSUPPORTED | 不支持的导出格式 |
| EXPORT_RENDER_FAILED | SVG 或 PNG 导出失败 |
| DOCUMENT_VERSION_CONFLICT | 文档保存时版本冲突 |
| QUOTA_NOT_ENOUGH | 积分不足 |
| TASK_CANCELED | 任务已取消 |
| TASK_EXPIRED | 任务已过期 |

---

## 十、文件管理

### 10.1 存储路径

~~~text
{STORAGE_DIR}/
  export/{YYYYMMDD}/{userId}/{documentId}/{uuid}.svg
  export/{YYYYMMDD}/{userId}/{documentId}/{uuid}.png
  export/{YYYYMMDD}/{userId}/{documentId}/{uuid}.mmd
  export/{YYYYMMDD}/{userId}/{documentId}/{uuid}.json
  temp/{YYYYMMDD}/{userId}/{taskId}/{uuid}.tmp
~~~

### 10.2 输出命名

| 格式 | 扩展名 | 示例 |
|------|--------|------|
| SVG | .svg | 请假审批流程.svg |
| PNG | .png | 请假审批流程.png |
| Mermaid | .mmd | 请假审批流程.mmd |
| JSON | .json | 请假审批流程.json |

文件名经过平台安全清理：移除路径分隔符、控制字符和保留名称，存储路径始终使用 UUID。

### 10.3 安全规则

1. 下载请求必须验证 user_id，或返回短期签名 URL。
2. 对象存储路径不可由客户端直接指定。
3. Worker 写入导出文件前校验文件格式、MIME、大小和渲染结果有效性。
4. 导出文件、临时文件和任务到期后自动清理。
5. 供应商结果 URL 必须通过可信域名、重定向和内容大小校验。
6. 用户只能读取本人 document_id、task_id 和 file_id。
7. 字体文件只从项目维护的许可白名单加载，禁止将用户上传字体带入预览或导出 Worker。

---

## 十一、模型 API 网关设计

### 11.1 统一接口

~~~python
class ModelProvider:
    async def submit(self, request: dict) -> ProviderSubmission:
        ...

    async def poll(self, submission: ProviderSubmission) -> ProviderPollResult:
        ...

    async def cancel(self, submission: ProviderSubmission) -> None:
        ...

    async def health_check(self) -> ProviderHealth:
        ...
~~~

所有适配器必须将供应商的同步或异步响应转换为统一结构。业务服务只依赖统一接口，不依赖某一家模型的字段、鉴权方式和状态码。

### 11.2 OpenAI 兼容适配器

OpenAICompatibleProvider 负责：

1. 从安全配置读取 base URL、API Key、模型名和协议差异。
2. 将 DiagramDocument JSON Schema 转换为供应商可接受的 response_format、JSON mode 或提示词约束。
3. 注入 idempotency_key、超时和追踪请求 ID。
4. 将普通文本、结构化响应或任务 ID 转换为 ProviderSubmission。
5. 将 HTTP 429、5xx、网络错误映射为可重试错误；将 4xx 参数或内容安全错误映射为终态错误。

### 11.3 原生适配器

NativeProvider 用于非兼容 API。每个适配器只处理该供应商的鉴权、请求格式、异步任务查询、取消和结果转换；不得将供应商特定字段泄漏到 API 层。

新增供应商的最小接入条件：

1. 实现 submit、poll、cancel、health_check。
2. 通过 Provider 合约测试。
3. 标注同步或异步能力、结构化输出能力、超时和最大并发。
4. 在测试环境验证 JSON Schema 校验、重试、取消和日志脱敏。

### 11.4 容灾与降级

| 场景 | 策略 |
|------|------|
| 供应商未启用 | 不加入路由候选 |
| 健康检查失败 | 暂时熔断并使用其他已启用候选 |
| 提交前连接失败 | 可切换到下一优先级候选 |
| 已获取供应商任务 ID | 不因单次轮询异常自动切换，优先继续轮询或超时取消 |
| 明确可重试终态错误 | 确认未产生可计费结果后可降级 |
| 内容安全或参数错误 | 不降级，直接提示用户修改描述 |

### 11.5 成本控制与观测

1. 按用户、IP、应用、供应商和模型维度限流。
2. 创建生成任务时冻结积分，确认成功后扣减，失败或取消退款。
3. 每次 submit、poll、cancel 都写 flowchart_provider_call。
4. 监控 queue_wait_ms、provider_wait_ms、render_duration_ms、poll_count、retry_count、成功率和超时率。
5. 降级必须记录 fallback_reason，便于判断供应商质量和成本。
6. 管理员仅通过安全配置调整优先级、并发、超时和成本；不通过用户接口暴露密钥。

---

## 十二、部署架构

~~~text
┌─────────────────┐       iframe / postMessage      ┌───────────────────────────────┐
│ AI 应用广场      │ ◄──────────────────────────────► │ AI 生成流程图                  │
│ 用户 / 认证 / 扣费│                                  │                               │
└─────────────────┘                                  │ ┌──────────┐ ┌────────────┐ │
                                                       │ │ Nginx    │ │ FastAPI    │ │
                                                       │ │ 前端静态 │ │ API + SSE  │ │
                                                       │ └──────────┘ └─────┬──────┘ │
                                                       │                     │        │
                                                       │             ┌───────▼──────┐ │
                                                       │             │ Celery Worker │ │
                                                       │             │ submit / poll │ │
                                                       │             │ export        │ │
                                                       │             └───────┬──────┘ │
                                                       └─────────────────────┼────────┘
                                                                             │
                  ┌────────────────────┬───────────────────┬───────────────▼──────────────┐
                  │ PostgreSQL          │ Redis             │ OSS / MinIO                  │
                  │ 文档 / 任务 / 日志   │ 队列 / 限流 / 事件  │ 导出文件 / 临时结果            │
                  └────────────────────┴───────────────────┴──────────────────────────────┘
                                                                             │
                                             ┌───────────────────────────────▼──────────────┐
                                             │ 已启用的国内外模型 API                        │
                                             │ OpenAI compatible / Native Provider adapters  │
                                             └───────────────────────────────────────────────┘
~~~

### 本地开发启动

~~~bash
# 后端 API：本机 Python 3.12.10，由 uv 管理项目 .venv
cd backend
uv sync
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Celery Worker：使用同一个 uv 项目环境
cd backend
uv run celery -A app.workers.celery_app worker -l info

# Celery Beat：补偿遗漏的供应商轮询和清理任务
cd backend
uv run celery -A app.workers.celery_app beat -l info

# 前端：本机 Node.js 20.19.0、React/Vite 与项目内 pnpm 11.16.0
# 仅使用项目内 pnpm.cmd，不使用 pnpm 全局安装命令
cd frontend
pnpm.cmd install
pnpm.cmd dev -- --host 127.0.0.1 --port 5777
~~~

启动顺序：先启动 Docker Desktop 并确认 Docker Engine 可用 → PostgreSQL 和 Redis → Worker 与 Beat → FastAPI → React 前端。模型配置通过服务端安全配置提供；没有已启用模型时，前端应显示“暂无可用模型”，而不是尝试读取本地密钥。

### Docker 部署

~~~bash
# 先在 Windows 中启动 Docker Desktop，再确认 Engine 已连接
docker version
docker compose up -d
~~~

Docker Compose 包含 PostgreSQL、Redis、MinIO、FastAPI、Celery Worker、Celery Beat、前端 Nginx。本次环境盘点中 Docker 客户端和 Compose 已安装，但 Docker Desktop Engine 尚未启动；启动后可直接使用上述命令。生产环境使用受管数据库、受管对象存储和专用密钥管理服务替代开发容器。

---

## 十三、功能实现总结

| 功能 | 可行性 | 实现方式 | 优先级 |
|------|--------|----------|--------|
| 描述输入、模板和画布工作台 | ✅ | React + Ant Design + Zustand | P0 |
| 节点编辑与连线 | ✅ | React Flow 自定义节点和边 | P0 |
| 自动布局 | ✅ | dagre | P0 |
| Mermaid 源码生成 | ✅ | DiagramDocument 编译器 | P0 |
| Mermaid 导出 | ✅ | 文本文件生成 | P0 |
| SVG / PNG 导出 | ✅ | Mermaid CLI 或受控渲染任务 | P0 |
| 结构化模型生成 | ✅ | JSON Schema + Pydantic 校验 | P0 |
| OpenAI 兼容 API | ✅ | 通用 httpx 适配器 | P0 |
| 原生 API 适配器 | ✅ | Provider 协议和按需 Adapter | P1 |
| 同步模型调用 | ✅ | submit 后直接校验结果 | P0 |
| 异步模型轮询 | ✅ | Celery 延迟任务 + PostgreSQL next_poll_at | P0 |
| 超时、取消与补偿扫描 | ✅ | deadline_at、cancel、Celery Beat | P0 |
| 供应商容灾 | ✅ | Router、健康检查和安全降级 | P1 |
| 最近文档和个人模板 | ✅ | PostgreSQL | P1 |
| 局部重新生成 | ✅ | 节点子图 Prompt 与文档版本 | P2 |
| 多人协作 | ✅ | 文档版本、实时协作协议 | P3 |
| BPMN / UML / 泳道图 | ✅ | 新的中间结构和渲染映射 | P3 |

---

## 十四、分期计划

### 一期 MVP

1. AI 应用广场 iframe 认证与 Token 透传。
2. 流程描述输入、内置模板和单页工作台。
3. DiagramDocument JSON Schema、Mermaid 编译和 React Flow 画布。
4. 节点编辑、连线、自动布局、撤销重做和文档保存。
5. OpenAI 兼容 Provider Gateway。
6. 本地异步任务、Celery Worker、供应商 submit 和 poll。
7. 退避轮询、超时、取消、幂等、刷新恢复和 Beat 补偿扫描。
8. SVG、PNG、Mermaid、JSON 导出。
9. 积分冻结、成功扣减、失败退款、用量上报和结果文件清理。

### 二期增强

1. 按用户提供的 API 接入原生 Provider。
2. 健康检查、限流、熔断和安全自动降级。
3. 最近文档、个人模板和分类模板库。
4. 节点局部重新生成与描述优化。
5. 导入 Mermaid 和 JSON。
6. 更丰富的节点样式、对齐、分组和导出主题。

### 三期运营化

1. BPMN、UML、泳道图、时序图等多图类型。
2. 多人协作、评论、版本对比和权限管理。
3. 供应商成本分析、质量评估和路由策略调优。
4. 模板市场、组织模板和运营后台。
5. 可观测性看板：队列时延、模型时延、轮询次数、成功率和成本。
