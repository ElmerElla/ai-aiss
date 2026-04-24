# AI 校园助手前端

本项目基于 Vue 3 + Vite 构建，提供校园人工智能助手的用户界面。

## 快速开始

```bash
# 1. 进入项目目录
cd frontend/ai_assistant

# 2. 安装依赖
npm install

# 3. 创建环境变量文件（必须与后端 AES_SECRET_KEY 一致）
cp .env.example .env
# 编辑 .env → VITE_AES_SECRET_KEY=<你的后端AES密钥>

# 4. 确保后端在 localhost:8000 运行

# 5. 启动开发服务器
npm run dev
# → 访问 http://localhost:5173

# 6. 构建生产版本
npm run build
# → 输出到 dist/ 目录
```

## API 接口变更说明

当前项目已接入后端的最新的 Server-Sent Events (SSE) 流式接口。

- **请求方式**: `POST /api/v1/query`
- **处理方式**: 前端 `queryApi.askStream` 使用 `fetch` 和 `TextDecoder` 读取流式 `data: {...}` 对象，解决传统 HTTP 长耗时的等待问题。
- **状态管理**: 消息渲染由 Pinia 状态管理 `chatStore` 内维护，使用响应式 Proxy 监听实现逐字打印效果。