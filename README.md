AI Writer 智能写作助手

集知识库管理、长文生成与 OpenWPS 知识写作于一体的 Web 应用。模型 / Embedding / 向量库 / MinerU 全部走云端 API，本地仅持久化业务数据。

更详细的部署、排错、模块说明见 [DEPLOYMENT.md](./DEPLOYMENT.md)。

## 功能模块

- **知识库**：MinerU 文档解析（API 模式），PDF / Office 文件上传后自动提取为可检索的 Markdown，支持在线预览。
- **AI 知识问答**：基于 RAG 的语义检索 + LLM 生成，云端 / 本地模型可切换。
- **长文生成**：主题 → 大纲 → 章节 → Word 导出 的端到端流水线，支持人工编辑大纲与重生成。
- **OpenWPS 知识写作**：ProseMirror 富文本编辑器 + Agent ReAct 流程，工具系统覆盖排版、查找、表格、图片、Mermaid、子代理等。
- **联网工具**：Tavily API（推荐，无头友好）/ 本地 Chrome CDP（开发用）双通道。

## 技术栈

- 前端：Vue 3 + TypeScript（主站） / React + ProseMirror（OpenWPS 写作）
- 后端：FastAPI + LangGraph，OpenWPS 作为 sub-app 挂载在 `/openwps`
- 模型：DeepSeek（聊天）+ SiliconFlow / OpenAI 兼容（Embedding）
- 向量库：Milvus / Zilliz Cloud（远端），无配置时回退到本地 JSON 存储
- 文档解析：MinerU 在线 API

## 快速开始 — Docker（推荐）

前置条件：Docker、Docker Compose v2、4GB+ 可用内存。

```bash
# 1. 克隆并配置
git clone <repo-url>
cd AI_Writer
cp .env.example .env
# 编辑 .env，至少填：DEEPSEEK_API_KEY、EMBEDDING_API_KEY、MINERU_API_TOKEN
# 如需远端向量检索，再填 MILVUS_URI / MILVUS_USER / MILVUS_PASSWORD

# 2. 构建并启动
docker compose up --build -d

# 3. 验证
curl http://localhost:28000/health   # 后端健康检查
open http://localhost:5173           # 浏览器访问主站
```

| 服务 | 地址 |
|---|---|
| 主站 | http://localhost:5173 |
| 后端健康检查 | http://localhost:28000/health |
| OpenWPS 知识写作 | http://localhost:5173/workspace-agent |

容器停止 / 清理：

```bash
docker compose down        # 停止
docker compose down -v     # 停止并清空所有数据卷
docker compose logs -f backend
```

## 快速开始 — 本地开发

主站（Vue 3 + Vite）：

```bash
# 后端
python3 -m venv backend/venv
source backend/venv/bin/activate
pip install -r backend/requirements.txt
backend/venv/bin/python3 -m uvicorn app.main:app --host 0.0.0.0 --port 28000 --app-dir backend

# 前端（新终端）
cd frontend
npm install
npm run dev   # 5173，自动 proxy /api 与 /openwps 到 28000
```

OpenWPS 写作前端（React + Vite，独立 dev server）：

```bash
cd openwps_frontend
npm install
npm run dev    # 仍走 5173 端口结构，注意：
               # vite.config.ts 已修复，仅 /openwps/api 转后端，HTML/JS 由 vite 提供
               # 否则 /openwps/ 会被后端 dist 接管，HMR 失效
```

> 重要：`openwps_frontend` 改动后必须用 `npm run dev` 跑 vite 开发服务器，
> 直接刷新浏览器看不到变化是因为后端 SPA fallback 会回退到 `dist/index.html`。
> 部署到 Docker 时，容器构建阶段会自动 `npm run build` 生成 dist。

## 必填环境变量

| 变量 | 说明 |
|---|---|
| `DEEPSEEK_API_KEY` | DeepSeek 聊天模型 Key |
| `EMBEDDING_API_KEY` | Embedding API Key（SiliconFlow / OpenAI 兼容） |
| `MINERU_API_TOKEN` | MinerU 文档解析 Token |
| `MILVUS_URI` / `MILVUS_USER` / `MILVUS_PASSWORD` | 远端向量库（不填会回退本地 JSON） |

完整变量表见 [DEPLOYMENT.md](./DEPLOYMENT.md#环境变量)。

## 持久化数据

Docker 数据卷（详见 `docker-compose.yml`）：

| 卷 | 路径 | 内容 |
|---|---|---|
| `backend_data` | `/app/backend/data` | SQLite、本地 JSON 存储 |
| `backend_uploads` | `/app/backend/uploads` | 上传原文件 |
| `backend_parsed_output` | `/app/backend/parsed_output` | MinerU 解析产物 |
| `openwps_data` | `/app/openwps_server/data` | OpenWPS 工作区、会话、版本快照 |
| `openwps_config` | `/app/openwps_server/config` | OpenWPS 配置 |

## 常见问题

- **OpenWPS 文档显示空白但工具显示成功**：dev 用 vite proxy 时 HTML 不能让后端 dist 接管，已在 `openwps_frontend/vite.config.ts` 修复。Docker 部署不受影响。
- **DeepSeek 400 错误**：`tool_calls` 顺序与 `reasoning_content` 回传问题已在代码中处理，详见 [DEPLOYMENT.md 排错](./DEPLOYMENT.md#排错)。
- **Embedding 403**：检查 `EMBEDDING_API_KEY`。
- **联网搜索失败**：Docker 部署需要配置 Tavily；本地需要按 [DEPLOYMENT.md 联网搜索说明](./DEPLOYMENT.md#联网搜索说明) 启用 CDP。
- **MinerU 本地 conda 环境**：本项目默认走 API 模式，无需本地安装。如需自托管解析，参考 MinerU 官方仓库 [opendatalab/MinerU](https://github.com/opendatalab/MinerU)。

## 目录结构

```
AI_Writer/
├── backend/              # FastAPI 主后端 + 长文生成
├── frontend/             # Vue 3 主站（知识库 / 长文生成 / 入口）
├── openwps_frontend/     # React + ProseMirror 知识写作前端
├── openwps_server/       # OpenWPS FastAPI sub-app + Node 文档 worker
├── deploy/               # nginx 配置（Docker 前端用）
├── docker-compose.yml
├── DEPLOYMENT.md         # 详细部署 / 架构 / 排错
└── README.md
```

## License

MIT
