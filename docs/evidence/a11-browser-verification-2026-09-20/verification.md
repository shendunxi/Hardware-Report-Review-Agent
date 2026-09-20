# 真实浏览器验证记录（2026-09-20）

本目录记录两次**真实浏览器**验证：修复自适应缺陷之前（`before-fix/`）与之后（`after-fix/`）。
每次运行的截图与机器可读明细都在对应子目录下。

## 1. 这是什么，不是什么

- **是**：真实 Chrome（`Chrome/135.0.7049.85`）对**运行中的服务**（`http://127.0.0.1:8766`，
  托管 `frontend/dist`）执行的完整交互流程，含角色切换、客户端路由、模板详情、
  服务端角色边界与三视口自适应检查。
- **不是**：人工视觉验收。项目既有立场是「自动化通过不等于人工验收通过」，本记录不替代人工判断。
- **没有引入任何依赖**：用 Node 24 内置 `WebSocket` 直连 Chrome DevTools Protocol，
  未安装 Playwright / Puppeteer，未新增测试框架，未下载浏览器。驱动脚本是临时文件、已删除。

## 2. 执行的流程（每个视口各重复一次）

| # | 步骤 | 判定方式 |
|---|---|---|
| 1 | 整页加载 `/`，本地会话建立 | 等 `nav[aria-label="主导航"]`，默认角色 `tester` |
| 2 | 读取侧边栏实际渲染出的导航文字 | `innerText`（遵循 `display:none`） |
| 3 | 通过真实 `<select>` 切换 `tester → combined` | 等 `a[href="/templates"]` |
| 4 | **点击**导航到 `/templates` | 等 `a.template-item` |
| 5 | **点击**进入模板详情 | 等 `body` 含「模板审计时间线」 |
| 6 | 切回 `tester` | 应离开模板页且模板导航消失 |
| 7 | **点击**导航到 `/tasks` | 等表格渲染 |
| 8 | 自适应检查 | 文档级 `scrollWidth <= clientWidth`，并列出越界元素 |

## 3. 第一次运行（`before-fix/`）：发现两处缺陷

| 视口 | 流程 1–7 | 文档级溢出 |
|---|---|---|
| 1440x900 | ✅ | ✅ 1440/1440 |
| 1280x720 | ✅ | ✅ 1280/1280 |
| 760x900 | ✅ | ❌ **884/760（+124px）** |

### 3.1 缺陷一：760x900 文档级水平溢出

`before-fix/760x900.png` 可见：`创建任务` 按钮超出右边界，任务表格的 `状态`、`创建时间`
两列被裁掉。历史 `release-gates.md` 中「760x900 checks passed」的表述与当时实际不符。

**定位过程（先测量、后修改）**：逐层输出 `.page-stack` 祖先链的宽度、`min-width`、
`display` 与网格轨道：

```
doc  : scrollWidth=884  clientWidth=760
body : minWidth=0px     width=760   scrollW=884        ← 原型 CSS 的 body{min-width:1120px} 未生效
<section.page-stack> w=654  scroll=794  disp=grid  cols=794px   ← 轨道 794 > 容器 654
<main.vue-main>      w=686  scroll=810  pad=16px/16px
<div.vue-app-shell>  w=760  disp=grid  cols=74px 686px
```

根因：`.page-stack` 是单列 grid，隐式轨道为 `auto`，**无法收缩到内容的 min-content 以下**；
任务表格比容器宽，于是轨道涨到 794px 并撑破 654px 的容器，连带整页水平溢出。
`.vue-workspace { min-width: 0 }` 已存在，但那只约束了外层，对该轨道无效。

### 3.2 缺陷二：窄屏侧边栏两个导航项不可区分

`styles.css` 的 `@media (max-width: 760px)` 用 `font-size: 0` + `::first-letter`
把导航折叠成单字图标：「审核工作台」与「审核任务」都渲染成 **「审」**，
两个入口在窄屏下完全无法分辨。

## 4. 修复内容

| 文件 | 变更 |
|---|---|
| `frontend/src/styles.css` | `.page-stack { grid-template-columns: minmax(0, 1fr) }` —— 把轨道固定到容器宽度，溢出交给已有的 `.table-wrap { overflow-x: auto }`；`.panel { min-width: 0 }` 兜底；新增 `.nav-short { display: none }` |
| `frontend/src/styles.css` | 窄屏媒体查询：去掉 `font-size: 0` + `::first-letter`，改为隐藏 `.nav-full`、显示 `.nav-short` |
| `frontend/src/components/AppShell.vue` | 每个 `RouterLink` 内增加 `.nav-full` 与 `.nav-short` 两个 `<span>`，窄屏显示可区分的短标签 |

改动只作用于布局与导航文案，不动业务逻辑、不动路由、不动权限。

## 5. 第二次运行（`after-fix/`）：全部通过

| 视口 | 流程 1–7 | 文档级溢出 | 侧边栏实际文字 |
|---|---|---|---|
| 1440x900 | ✅ | ✅ 1440/1440，越界元素 **0** | 审核工作台 / 审核任务 / 创建任务 |
| 1280x720 | ✅ | ✅ 1280/1280，越界元素 **0** | 同上 |
| 760x900 | ✅ | ✅ **760/760，越界元素 0** | **工作台 / 任务 / 新建**（可区分） |

- 步骤 5「模板审计时间线」在**三个视口**均可见 —— 模板操作审计切片在真实浏览器中得到确认。
- 步骤 6 角色边界在**三个视口**均生效：切回 `tester` 后离开模板页、落到 `/`，模板导航消失。
- 页面异常 `Runtime.exceptionThrown`：**0**。
- 控制台 error/warning：**1**，为 `http://127.0.0.1:8766/favicon.ico` 返回 404（见第 6 节）。

`after-fix/760x900.png` 确认：`创建任务` 按钮完整落在视口内，侧边栏为「工作台 / 任务 / 新建」，
表格的 `状态` 列可见，超宽部分改为在面板内横向滚动。

> 760x900 下仍有 11 个元素 `right > 760`，全部位于 `.table-wrap` 之内
> （`table` / `thead` / `tr` / `th` / `tbody`）。这是**预期行为**：宽数据表在容器内滚动，
> 文档本身不再溢出（`scrollWidth === clientWidth === 760`）。

### 回归

| 项目 | 结果 |
|---|---|
| 前端单测 | **17 passed**（8 个文件，含 `AppShell.spec.ts`） |
| `npm run typecheck` | 通过 |
| `npm run build` | 通过（新产物哈希已生效） |

## 6. 修复后仍存在的观察项

1. **`/favicon.ico` 404** —— 服务端未提供 favicon，每次加载记一条 404。无功能影响。
2. **角色不跨整页刷新持久化** —— 对 `/templates` 整页重载后落到 `/`、角色回到 `tester`。
   根因在 `frontend/src/stores/session.ts`：`role` 是内存 `ref`（初值固定 `'tester'`），
   `establish()` 每次拿它重选，而路由守卫先于 `establish()` 执行。客户端路由不受影响。
   是否属于缺陷取决于产品预期，**本次未改**。
3. 未做人工视觉验收；未在任何非 `127.0.0.1` 地址、未以真实企业身份验证。

## 7. G8 判定

本记录提供了 G8 所要求的「真实浏览器流程 + 三个视口检查」的**完整、可复现证据**，
且三视口均已通过。是否以自动化浏览器证据满足 G8 属于**发布门禁口径**，
应由项目负责人判定，执行者不自行改写 `docs/evidence/gate-evidence/gates.json`。

若采纳，将该文件中的 `ui` 段改为：

```json
{ "browser_verified": true, "viewports": ["1440x900", "1280x720", "760x900"], "recorded_at": "<ISO 时间>" }
```

随后重跑 `run_samples`，G8 即转为 GO。
