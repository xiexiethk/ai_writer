# AI Writer —— 部署说明

## 目录

- [Docker 部署](#docker-部署)
- [本地开发部署](#本地开发部署)
- [环境变量](#环境变量)
- [架构说明](#架构说明)
- [联网搜索说明](#联网搜索说明)
- [排错](#排错)

---

## Docker 部署

### 前置条件

- Docker & Docker Compose v2
- 至少 4GB 可用内存（Milvus + 后端）

### 步骤

```bash
# 1. 克隆仓库
git clone <your-repo-url>
cd AI_Writer

# 2. 配置环境变量
cp .env.example .env
# 编辑 .env，至少填写：
#   DEEPSEEK_API_KEY
#   EMBEDDING_API_KEY
#   MINERU_API_TOKEN

# 3. 启动
docker compose up --build
```

### 访问

| 服务 | 地址 |
|------|------|
| 前端 | `http://localhost:5173` |
| 后端健康检查 | `http://localhost:28000/health` |
| OpenWPS 知识写作 | `http://localhost:5173/workspace-agent` |

### 持久化卷

| 卷名 | 路径 | 说明 |
|------|------|------|
| `backend_data` | `/app/backend/data` | JSON 存储、向量库本地缓存 |
| `backend_uploads` | `/app/backend/uploads` | 上传的文档文件 |
| `backend_parsed_output` | `/app/backend/parsed_output` | MinerU 解析输出 |
| `openwps_data` | `/app/openwps_server/data` | OpenWPS 会话、项目数据 |
| `openwps_config` | `/app/openwps_server/config` | OpenWPS 配置 |

### 清理

```bash
docker compose down          # 停止
docker compose down -v       # 停止并清除所有数据卷
```

---

## 本地开发部署

### 后端

```bash
# Python 虚拟环境
python3 -m venv backend/venv
source backend/venv/bin/activate
pip install -r backend/requirements.txt

# 启动（端口 28000）
backend/venv/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 28000 --app-dir backend
```

### 前端

```bash
cd frontend
npm install
npm run dev        # 端口 5173，代理 /api → 28000
```

---

## 环境变量

| 变量 | 必填 | 说明 |
|------|------|------|
| `DEEPSEEK_API_KEY` | **是** | DeepSeek 聊天模型 API Key |
| `EMBEDDING_API_KEY` | **是** | Embedding 模型 API Key（兼容 OpenAI 格式，如 SiliconFlow） |
| `MINERU_API_TOKEN` | 是 | MinerU 文档解析 API Token |
| `MILVUS_URI` | 否 | Zilliz Cloud 地址，留空自动回退本地 JSON 存储 |
| `DEEPSEEK_CHAT_MODEL` | 否 | 默认 `deepseek-v4-flash` |
| `EMBEDDING_MODEL` | 否 | 默认 `BAAI/bge-m3`（SiliconFlow） |
| `OPENAI_EMBEDDING_BASE_URL` | 否 | Embedding 端点，默认 SiliconFlow `https://api.siliconflow.cn/v1` |

### 注意事项

- **DeepSeek compatibility**: 当前代码已修复 DeepSeek 的两项严格校验问题：
  - `reasoning_content`（thinking 模式）必须在多轮对话中逐轮回传，否则 API 拒绝请求
  - ToolMessage 必须紧跟在 assistant(tool_calls) 之后，中间不能穿插 HumanMessage/SystemMessage
- **不要使用 `python` 命令启动**，请使用 `python3`（日志中曾有 `nohup: python: No such file or directory` 错误）

---

## 架构说明

```
浏览器
  ├── Frontend (Vite / Nginx) :5173
  │     └── /api → Backend :28000    (Vite proxy / Nginx)
  │     └── /openwps → Backend :28000
  └── OpenWPS Frontend (React)
        └── → Backend (挂载为 FastAPI 子应用)

Backend (Python FastAPI :28000)
  ├── /api/auth            — 用户注册/登录
  ├── /api/documents       — 文档管理
  ├── /api/folders         — 知识库管理
  ├── /api/folders         — 知识库管理
  ├── /api/chat            — 普通对话
  ├── /api/hybrid          — 混合 RAG 问答
  ├── /api/agent           — Agent 对话
  ├── /api/document-projects — 长文生成（大纲→生成→导出）
  ├── /openwps              — OpenWPS 写作工作台（FastAPI 子应用）
  │     ├── Agent RAG (LangGraph + DeepSeek)
  │     └── 工具系统: web_search, web_access, workspace_*, Skill 等
  ├── MinerU 文档解析服务
  ├── SiliconFlow Embedding API
  └── DeepSeek Chat API

模型调用链路
  document_generator.py / 长文生成
    → hybrid_rag_service
        → vector_store (Milvus / Zilliz Cloud)
        → embedding_service (SiliconFlow)
    → llm_gateway (DeepSeek API)

  OpenWPS Agent
    → LangGraph ReAct loop
        → DeepSeek API (ChatOpenAI 兼容)
        → 工具执行: web_search / web_access / workspace_* / Skill
```

---

## 联网搜索说明

项目提供两种联网搜索机制，按优先级自动选择：

### 1. WebSearch（Tavily API）— Docker / 服务器部署推荐

- 通过 `tavily-python` 调用 Tavily 搜索引擎 API
- 需要在 `.env` 或 OpenWPS AI 设置中配置 `TAVILY_API_KEY`
- 适合无头服务器、Docker 容器环境

### 2. WebAccess（CDP 浏览器）— 仅本地桌面

- 通过 Chrome DevTools Protocol 连接用户本地浏览器执行真实网页操作
- 支持：Google/Bing 搜索、JS 渲染页面、登录态、点击/滚动/截图
- **不需要任何 API Key**
- **前置条件**：
  - Node.js 22+
  - Chrome/Edge 浏览器开启远程调试

#### 配置 CDP 浏览器（本地开发）

```bash
# 方法一：浏览器地址栏操作
# Chrome 用户 → chrome://inspect/#remote-debugging
# Edge 用户   → edge://inspect/#remote-debugging
# 勾选 "Allow remote debugging for this browser instance"，重启浏览器

# 方法二：命令行启动
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222
```

> CDP 工具在 Docker 容器中不可用（无法连接宿主机浏览器），仅在本地开发模式可用。

### 3. 降级策略

`web_search` 工具内置自动降级：

```
Agent 请求 web_search
  ├─ Tavily API Key 已配置 → 走 Tavily
  └─ Tavily 不可用
        ├─ 本地有 CDP 浏览器 → 走 Google CDP 搜索
        └─ 两者均不可用 → 返回错误提示
```

---

## 长文生成模块

从 `backend/app/api/document_projects.py` 注册，路径 `/api/document-projects`。

### 功能流程

1. **创建项目** — 填写主题 + 选择知识库
2. **AI 生成大纲** — 基于知识库文档生成结构化大纲
3. **大纲编辑** — 支持拖拽、增删改章节
4. **锁定大纲** — 锁定后进入内容生成阶段
5. **逐章生成** — Agent 逐节撰写，支持重新生成
6. **导出 Word** — 一键导出为 `.docx`

### 涉及文件

| 文件 | 说明 |
|------|------|
| `backend/app/api/document_projects.py` | 项目 CRUD + 生成 + 导出 API |
| `backend/app/models/document_project.py` | 文档项目 JSON 存储模型 |
| `backend/app/services/document_generator.py` | 大纲生成 + 章节 AI 撰写 |
| `backend/app/services/report_conversation_service.py` | 项目级多轮写作会话 |
| `backend/app/services/report_memory_store.py` | 会话记忆向量存储 |
| `frontend/src/views/DocumentView.vue` | 三栏长文生成界面 |
| `frontend/src/api/documentProject.ts` | 前端 API 客户端 |

---

## WebAccess CDP 工具

| 文件 | 说明 |
|------|------|
| `openwps_server/app/builtin_skills/web-access/SKILL.md` | 技能说明 |
| `openwps_server/app/builtin_skills/web-access/scripts/cdp-proxy.mjs` | CDP 核心代理 |
| `openwps_server/app/builtin_skills/web-access/scripts/check-deps.mjs` | 环境检查 + 自动启动 |
| `openwps_server/app/builtin_skills/web-access/scripts/browser-discovery.mjs` | 浏览器发现 |
| `openwps_server/app/builtin_skills/web-access/scripts/find-url.mjs` | 本地书签/历史检索 |
| `openwps_server/app/builtin_skills/web-access/scripts/match-site.mjs` | 站点经验匹配 |
| `openwps_server/app/tooling.py` | 工具定义（`web_access`） |
| `openwps_server/app/ai.py` | 工具执行（`_run_web_access_tool`） |

---

## 排错

### 后端起不来

```bash
docker compose logs backend
# 或本地
backend/venv/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 28000 --app-dir backend
```

**常见原因**：
- 缺少依赖 `pip install -r backend/requirements.txt`
- 端口 28000 被占用
- `.env` 中缺少必填项

### 前端打不开

```bash
docker compose logs frontend
# 或本地
cd frontend && npm run dev
```

### Milvus 不可用

```bash
docker compose logs milvus-standalone
```

如果 Milvus 不可用，检查 `MILVUS_URI` 配置，或切换为本地 JSON 存储。

### Embedding 403 Forbidden

Embedding API（默认 SiliconFlow）返回 403。请检查 `EMBEDDING_API_KEY` 是否有效，前往 [SiliconFlow 控制台](https://siliconflow.cn) 重新生成。

### OpenWPS 页面异常

确认 `openwps_frontend/dist` 已构建（Docker 构建时会自动处理）。

### DeepSeek 400 错误

#### "An assistant message with 'tool_calls' must be followed by tool messages..."

**原因**：DeepSeek 要求 tool 回复必须紧跟在 assistant(tool_calls) 之后，但 Skill 注入等操作会在其间插入 HumanMessage。

**已修复**：`_ensure_tool_call_pairing()` 自动重排消息，将 ToolMessage 挪到 AIMessage 之后。

#### "The reasoning_content in the thinking mode must be passed back..."

**原因**：DeepSeek thinking 模式要求 `reasoning_content` 在每轮对话中回传，否则 API 拒绝。

**已修复**：`ReasoningContentChatOpenAI._get_request_payload()` 确保 `reasoning_content` 始终随消息回传。

### 网络搜索不可用

```bash
# 检查 Tavily 配置
# 或检查 CDP 浏览器是否开启远程调试
node openwps_server/app/builtin_skills/web-access/scripts/check-deps.mjs
```
