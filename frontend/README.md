# React (Umi) 前端模板

基于 **Umi Max** 的 React + Ant Design 前端脚手架，用于 Scaffold 生成项目。

## 快速开始

```bash
# 安装依赖
pnpm install

# 开发启动
pnpm dev

# 生产构建
pnpm build
```

## 目录结构

```
src/
├── access.ts              # 权限定义
├── app.ts                 # 运行时配置（layout、初始状态）
├── constants/             # 常量
├── components/            # 公共组件
│   └── Guide/             # 引导组件
├── models/                # 全局数据模型
├── pages/                 # 页面
│   ├── Home/              # 首页
│   ├── Access/            # 权限演示页
│   └── Table/             # CRUD 示例页
├── services/              # 接口服务
│   └── demo/              # 示例接口
├── utils/                 # 工具函数
└── assets/                # 静态资源
```

## 联调约定

| 项 | 约定 |
| ---- | ------ |
| API 前缀 | `/api`（proxy 到 `localhost:10105`） |
| 路由模式 | history（如需 hash 改 `.umirc.ts`） |
| 认证头 | `Authorization: Bearer <token>` |
| 响应格式 | `{ code, data, message }`，成功 code=200 |
| 字段风格 | camelCase |
| 密钥 | **禁止**把密码/token 写入前端环境变量 |

## 贡献

修改此模板后，请在 [AGENTS.md](./AGENTS.md) 中同步更新说明。

