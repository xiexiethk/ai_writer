---
name: web-access
version: "0.1.0"
source: https://github.com/eze-is/web-access
description:
  通过浏览器 CDP（Chrome DevTools Protocol）实现真实 Web 访问，取代传统 API 搜索。
  支持搜索、网页抓取、登录后操作、动态渲染页面等。
---

# Web Access —— 浏览器 CDP 联网

## 前置要求

- Node.js 22+
- Chrome / Edge 浏览器以远程调试模式运行
- CDP Proxy 通过 `check-deps.mjs` 自动管理

## 工具选择

| 场景 | 工具 |
|------|------|
| 搜索摘要或关键词结果，发现信息来源 | **WebSearch**（Tavily 快速搜索） |
| URL 已知，需要从页面定向提取特定信息 | **WebFetch**（HTTP 直接拉取） |
| 非公开内容、JS 渲染、需要登录态 | **Browser CDP**（通过 CDP Proxy） |
| 需要像人一样在浏览器内自由导航 | **Browser CDP** |

## CDP Proxy API

所有操作通过 HTTP API 调用本地 CDP Proxy：

```bash
# 检查环境并启动 Proxy
node "${SKILL_DIR}/scripts/check-deps.mjs"

# 列出已打开 tab
curl -s http://localhost:3456/targets

# 创建新后台 tab
curl -s "http://localhost:3456/new?url=https://example.com"

# 页面信息
curl -s "http://localhost:3456/info?target=ID"

# 执行任意 JS
curl -s -X POST "http://localhost:3456/eval?target=ID" -d 'document.title'

# 点击元素
curl -s -X POST "http://localhost:3456/click?target=ID" -d 'button.submit'

# 滚动
curl -s "http://localhost:3456/scroll?target=ID&y=3000"

# 关闭 tab
curl -s "http://localhost:3456/close?target=ID"
```

## 搜索策略

1. **WebSearch** 快速定位信息来源
2. 信息来源已知 → **WebFetch** 提取内容
3. 内容不可达（需登录/JS）→ **Browser CDP** 访问

## 信息核实

- 核实目标是一手来源（官网、官方平台）
- 非一手信息需向用户声明来源层级
