# AI 校园助手服务端 (AI Assistant)

本文档补充和说明了 AI 校园助手的整体架构设计、关键大模型 Prompt、AI 调用逻辑，以及在生产环境中的部署规范。

## 1. 架构说明

AI 校园助手采用前后端分离的现代化 Web 架构，核心侧重于通过大语言模型 (LLM) 提供智能化、强逻辑与严格保障隐私的问答服务。

- **前端架构 (Frontend)**：基于 Vue 3 + Vite 构建，集成 Tailwind CSS 进行响应式界面设计。采用防重放、密码传输加密 (CryptoJS AES) 机制保护用户信息。聊天交互采用 SSE (Server-Sent Events) 实现在线流式文本打印，还原类似 ChatGPT 的打字机体验。
- **后端架构 (Backend)**：采用 FastAPI (Python) 提供高并发的异步接口。
  - **ORM & 数据库**：通过 SQLAlchemy (AsyncIO) 访问底层的 MySQL 8.0 教务数据库。
  - **缓存体系**：采用 Redis 7 进行会话上下文暂存、限流及高频查询的缓存 (按敏感/非敏感级别区分 TTL)。
  - **大模型底座**：接入阿里云 DashScope (Qwen 系列)，借助 LangChain 框架进行多路智能执行编排。通过接入阿里云百炼检索 API 实现在线 RAG（检索增强生成）。
- **容器编排**：全套环境 (后端核心服务、MySQL 数据库连带数据卷、相关初始拉起脚本等) 采用 Docker Compose 统一部署，轻量且环境一致。

## 2. 关键 Prompt 与 Vibe 思路

项目中的 Prompt 设计强调“Vibe 理念”：即**打造一个懂变通、强隐私、高安全的校园贴心助手**，既能在无相关教务数据时优雅退让，又能把冷冰冰的各种数据字段转变为有温度的自然语言。

### 核心 Prompt 清单
1. **意图分类器 (Intent Classify Prompt)** 
   - *位置*: pp/services/intent_service.py
   - *思路*: 强制 LLM 仅输出 structured (结构化数据库查存)、ector (向量文档检索)、hybrid (混合查询) 之一。教导模型区分“规则政策”（必须去文档库查，如设备损坏怎么赔）与“教务数据”（必须去库里查，如成绩、课表）。
2. **多轮对话上下文重写 (Query Rewrite Prompt)**
   - *位置*: pp/services/intent_service.py
   - *思路*: 用户在后续提问中常使用代词或缩写（例如“那这门课呢？”、“导出上学期的”），该 Prompt 会结合最近 3-5 轮会话，指引 LLM 在不改变意图的情况下补全上下文，生成一个脱离上下文也能独立执行的标准 Query。对于结构化 SQL 查询的准确性至关重要。
3. **安全与自然语言转换 (Summary Prompt)**
   - *位置*: pp/services/intent_service.py
   - *思路*: **强制脱敏与友好化指令**。向模型注入当前系统时间（用于处理“今天”、“明天”、“下周”的时间相对词），且严格限定：1. 课表必须完整告知时间/地点/老师；2. **严禁在回答中暴露任何数据库字段名（如 student_id，major_id）**；3. 严禁越权查询他人隐私（越权发生时明确回复无权限）。
4. **混合查询重排器 (Hybrid Rerank Prompt)**
   - *位置*: pp/services/query_service.py
   - *思路*: 当命中的既有 SQL 数据又有文档检索知识时，引导 LLM 进行去重与相关性评分重过滤，确保输出到提示词窗口给生成大模型的 Context 信息是最精简且高密度的。

## 3. AI 调用逻辑

系统使用 **LangChain (LCEL)** 进行重构，构建了具备高度扩展性的并发调用逻辑，核心机制包括：

1. **动态意图路由 (Router)**：用户的普通文本经过历史记录 Rewriter 改写后，立刻交给 Qwen Turbo 做出意图路由检测。根据返回结果(structured / ector / hybrid)，将请求分配至不同的 Runnable Chain 代码分支处理。
2. **本地结构化转化 (Text2SQL / Function Calling)**：
   - 当路由至 structured 时，模型通过 LangChain 的相关 Agent 机制分析用户的自然语言查询约束（如“张三的软件工程课什么时候上”），动态生成过滤并将其交由后台安全沙箱运行取得结果。查询时后台会自动限定当前会话人的 User ID 以强制保障行级数据安全越权隔离。
3. **知识检索链路 (RAG)**：
   - 当路由到 ector 时，基于 BailianLangChainRetriever (封装好的阿里云百炼检索 API) 查取校园规定与文档切片，将召回的相关片段组装为 Context，抛给最终的 Generator LLM 总结。
4. **SSE 流式输出 (Streaming Output)**：
   - 最终总结阶段，使用 FastAPI 的 StreamingResponse 包装了 LangChain 的 stream_events 或事件型打字回调。
   - 每生成一个 Token（或一块 chunk），直接以 	ext/event-stream 推送到前端页面上进行实时渲染。不仅包含文本 Chunk，最后一条数据还会包含耗时、缓存状态（Cache Hit），丰富用户界面的细节展示。

## 4. 部署步骤说明（含 DNS/HTTPS）

生产环境推荐使用 Docker 引擎完成所有基础中间件与应用的托管。

### 基础部署
1. **环境准备**: 确保已安装 Docker 和 Docker Compose。
2. **拉取代码**: 
   `ash
   git clone <你的项目仓库地址>
   cd ai_assistant/service/ai_assistant/ai_assistant
   `
3. **配置环境**:
   - cp .env.example .env
   - 修改 .env 文件，按需填入各种安全密钥、MYSQL_PASSWORD、各种 API_KEY 和阿里云百炼检索的 ALIBABA_CLOUD_ACCESS_KEY_ID。
4. **一键启动**:
   `ash
   docker-compose up -d --build
   `
   *说明：此命令将自动拉起 MySQL 8 服务（并根据 init_sql 文件夹建库预填表）、Redis 缓存以及 FastAPI 核心服务节点。*

### DNS 解析与 HTTPS 反向代理说明

由于服务含带 SSE 流式以及可能的敏感数据提交，因此**生产级域名解析与 HTTPS 保护为强制建议配置项**：

1. **域名解析 (DNS)**
   - 在域名服务商（如阿里云、腾讯云等）的控制将子域名（如 i.xxx.edu.cn）通过 A 记录解析到运行此部署业务的云宿主机公网 IP。
2. **自建 Nginx/Caddy 网关支持 HTTPS**
   - 建议基于免费的 Let's Encrypt 证书申请 HTTPS 签发。
   - **Nginx 反向代理配置重点（适配 SSE/流式关键参数）**：
     针对此项目的 SSE 流式接口，为防止 Nginx 缓冲区卡住输出（导致前端无法像打字机一样呈现，而是一次性等很久同时弹出）：
     `
ginx
     server {
         listen 443 ssl;
         server_name ai.xxx.edu.cn;

         ssl_certificate /path/to/cert.pem;
         ssl_certificate_key /path/to/key.pem;

         location /api/ {
             proxy_pass http://127.0.0.1:8000;
             proxy_set_header Host $host;
             proxy_set_header X-Real-IP $remote_addr;
             proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;

             # 【关键配置】禁用缓冲支持 Server-Sent Events 流式
             proxy_buffering off; 
             proxy_cache off;
             proxy_set_header Connection '';
             proxy_http_version 1.1;
             chunked_transfer_encoding on;
         }
         
         # 静态资源请求代理至前端静态服务器或前端容器...
     }
     `
3. **验证流式接口测试**
   配置通过后，可通过访问 https://ai.xxx.edu.cn/api/v1/health 检查通断状况。