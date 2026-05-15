# AI Writer - Docker 完整功能部署（本地应用 + 云端模型/数据库）

AI Writer 是一个集知识库管理、长文生成与 OpenWPS 知识写作为一体的 Web 应用。

本部署方案的设计原则：
- **应用本身部署在 4090 服务器**
- **模型、Embedding、向量数据库、MinerU 都走云端 API / 云端服务**
- **本地只保存生成文档、上传文件、解析输出和运行数据**

## 前置要求
- 4090 服务器已安装 Docker 和 Docker Compose
- 你已经准备好云端服务的可用配置：
  - DeepSeek（聊天生成）
  - Embedding API（OpenAI 兼容 / SiliconFlow 等）
  - 云端 Milvus / Zilliz Cloud
  - MinerU API

## 1. 准备环境变量

```bash
cp .env.example .env
```

编辑根目录 `.env`，至少填写：
- `DEEPSEEK_API_KEY`
- `EMBEDDING_API_KEY` 或 `OPENAI_API_KEY`
- `MILVUS_URI`
- `MILVUS_USER`
- `MILVUS_PASSWORD`
- `MINERU_API_TOKEN`

### 重要说明
当前部署**不会**在本地启动 Milvus 容器。
向量检索链路默认连接你自己的**云端 Milvus / Zilliz**。

## 2. 构建并启动

前台启动：
```bash
docker compose up --build
```

后台启动：
```bash
docker compose up --build -d
```

## 3. 访问方式

启动成功后：
- 前端：`http://<4090服务器IP>:5173`
- 后端健康检查：`http://<4090服务器IP>:28000/health`

如果你在 Win / Mac 上访问，只要浏览器能访问 4090 的 IP 和端口即可。

## 4. 当前 Compose 包含的服务
- `frontend`：Vue 前端 + nginx
- `backend`：FastAPI + OpenWPS 集成服务

## 5. 功能范围
该 Docker 方案保留完整业务能力：
- 注册 / 登录
- 知识库管理
- 长文生成
- OpenWPS 知识写作
- 云端向量检索链路（Milvus / Zilliz）
- MinerU 在线解析
- Hosted LLM / Embedding 能力
- 文档导出 / 转换（依赖容器内 LibreOffice / wkhtmltopdf）

## 6. 常用命令
查看日志：
```bash
docker compose logs -f
```

停止服务：
```bash
docker compose down
```

删除容器并清理卷：
```bash
docker compose down -v
```

重新构建：
```bash
docker compose build --no-cache
```

## 7. 持久化数据
Compose 已为以下目录挂载 volume：
- SQLite 数据
- uploads
- parsed_output
- openwps_server/data
- openwps_server/config

这些是**本地持久化数据**，主要保存：
- 上传文档
- 解析产物
- 生成文档
- OpenWPS 本地工作数据

## 8. 注意事项
- 首次构建 backend 会比较慢，因为容器内需要安装 LibreOffice / wkhtmltopdf 等完整文档处理依赖。
- 如果 `.env` 中云端 API key / 云端向量数据库配置错误，应用可以启动，但相关 AI / 检索功能会失败。
- 若要换云端 Milvus / Zilliz，只需修改 `.env` 中的 `MILVUS_URI / USER / PASSWORD`，不需要改 compose。

## 9. 目录结构
```text
AI_Writer/
├── frontend/
├── openwps_frontend/
├── openwps_server/
├── backend/
├── deploy/
├── docker-compose.yml
└── .env.example
```
