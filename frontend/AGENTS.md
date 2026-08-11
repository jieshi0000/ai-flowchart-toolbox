# React (Umi) 模板维护指南

## 项目概述

基于 Umi Max 4 + React 18 + Ant Design 5 的前端模板。Scaffold 中 `--umi` 或 `frontend.type=umi` 时使用此模板生成前端。

## 目录规范

```
src/
├── access.ts              # 权限定义（canSeeAdmin）
├── app.ts                 # 运行时配置（layout、getInitialState）
├── constants/             # 常量（DEFAULT_NAME → 流程图工具箱）
├── components/            # 公共组件
│   └── Guide/             # 引导组件示例
├── models/                # 全局数据模型（useModel）
├── pages/                 # 页面（按模块建文件夹）
├── services/              # 接口定义
├── utils/                 # 工具函数
└── assets/                # 静态资源
```

## 占位符说明

模板中的 `{{KEY}}` 由 scaffold `setup.sh` 的 `replace_placeholders` 替换：

| 占位符 | 文件 | 用途 |
| -------- | ------ | ------ |
| `流程图工具箱` | `.umirc.ts` | layout 标题 |
| `流程图工具箱` | `src/app.ts` | 运行时初始状态 |
| `流程图工具箱` | `src/constants/index.ts` | 常量 DEFAULT_NAME |
| `流程图工具箱` | `.env` | VITE_APP_TITLE |
| `10105` | `.umirc.ts` | dev proxy 目标端口 |
| `10105` | `.env` | 后端端口环境变量 |
| `20105` | `.env` | 前端 dev 端口 |
| `flowchart-toolbox-server` | `nginx.conf` | 部署时后端 service |
| `8000` | `nginx.conf` | 部署时后端容器端口 |
| `20105` | `README.md` | 联调约定说明 |

新增占位符时，请同步添加到 `setup.sh` 的 `PLACEHOLDERS` 数组。

## 与后端联调约定

| 项 | 约定 |
| ---- | ------ |
| API 基础路径 | `/api`（无额外前缀） |
| 本地代理 | `pnpm dev` 时 Umi proxy `/api` → `http://localhost:10105` |
| 生产代理 | nginx `/api/` → `flowchart-toolbox-server:8000/api/` |
| 路由模式 | `history`（`.umirc.ts` 中配置） |
| 认证头 | `Authorization: Bearer <token>` |
| 公开配置 | `GET /api/public/config` → `{ authEnabled, captchaEnabled, ssoEnabled }` |
| JSON 字段 | 请求/响应 camelCase |
| 响应格式 | `{ code, data, message }`，成功 `code=200` |
| 写操作 id | 更新/删除：id 放 query，body 放业务字段 |
| 密钥 | **禁止**密码/token/client_secret 写入 `VITE_` 环境变量 |

## 密钥管理

前端不涉及数据库密码等敏感配置，但需注意：

- `VITE_` 前缀变量会被打包进前端代码，**禁止放任何密钥**
- `.env` 可提交 git（仅含端口、标题等非敏感信息）
- SSO client_id 等可放 `.env`，client_secret **绝不**放前端
## 新增页面流程

1. 在 `src/pages/` 下创建页面目录
2. 在 `src/services/` 下（或已有模块中）添加接口调用
3. 在 `.umirc.ts` 的 `routes` 中添加路由
4. 如需全局共享数据，在 `src/models/` 中添加 model


## 部署

全栈部署由项目根 `docker-compose.yml` 管理：

```yaml
services:
  flowchart-toolbox-server:  # 后端
    build: ./backend
  flowchart-toolbox-frontend:  # 前端
    build: ./frontend
```

`Dockerfile` 构建流程：`pnpm install` → `pnpm build` → nginx 承载静态文件。

`nginx.conf` 将 `/api/` 反向代理到 `flowchart-toolbox-server:8000`。
