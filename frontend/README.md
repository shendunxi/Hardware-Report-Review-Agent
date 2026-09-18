# Vue 前端

这是硬件测试报告审核智能体的正式前端，技术栈为 Vue 3、TypeScript、Vite、Vue Router 和 Pinia。页面只消费同源 `/api` 数据，不在浏览器内伪造任务或审核结论。

## 开发

```powershell
Set-Location 'E:\Coding\Hardware-Report-Review-Agent\frontend'
pnpm install
pnpm dev
```

开发服务器位于 `http://127.0.0.1:5173/`，并将 `/api` 转发到 `http://127.0.0.1:8766`。

## 测试与构建

```powershell
pnpm test
pnpm typecheck
pnpm build
```

构建产物写入 `frontend/dist/`。FastAPI 检测到该目录后，会在 `http://127.0.0.1:8766/` 提供 Vue 应用，并对 `/tasks/...`、`/templates/...` 等 history 路由返回 SPA 入口；`/api/*` 始终由后端路由优先处理。

## 当前边界

- “测试报告审核”和“模板规则管理”是当前正式角色名称；页面角色选择器是权限边界演示，不是身份认证。
- 开发数据库为 SQLite；生产数据库待定。
- 原报告和源模板不会被覆盖，审核完成后下载由智能体填写的 A11 XLS 副本。
- DOC 在当前仅有 WPS、无 genuine Microsoft Word 的主机上仍为未通过环境门禁；DOCX/XLSX 尚无真实样本验收证据。
