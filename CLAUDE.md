# CLAUDE.md

DeepSeek 开放平台用量监控桌面应用 — 抓取 platform.deepseek.com 的用量数据，实时展示余额、Token 用量、缓存命中率和各模型费用。

## 环境要求

- Python 3.8+
- Chromium 浏览器（系统已安装 Chrome/Edge，或 Playwright 自带的 Chromium）
- Windows 10/11（pywebview 依赖 Edge WebView2）

## 依赖

```
flask>=3.0          # Web 框架，仪表盘后端 API
playwright>=1.40     # 浏览器自动化，登录 DeepSeek 并抓取数据
httpx>=0.24          # 异步 HTTP 客户端，调用 DeepSeek 内部 API
pywebview>=6.0       # 桌面 GUI，用 Edge WebView2 套壳前端页面
```

安装: `pip install -r requirements.txt`

## 启动方式

```bash
python desktop.py              # 完整桌面应用（推荐）
python desktop.py --folded     # 启动后自动折叠为悬浮球（开机自启用）
python app.py                  # 仅 Flask Web 服务（开发调试，http://localhost:5000）
python float_ball.py           # 仅悬浮球（独立进程，连本地 Flask）
```

## 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| `CHROMIUM_PATH` | 系统 Chrome/Edge 路径，设置后跳过 Playwright 下载 | 空（使用 Playwright Chromium） |
| `DEEPSEEK_HEADED` | `1`/`true`/`yes` 开启有头模式，用于调试登录 | 空（headless） |

## 项目结构

```
desktop.py          → 入口：预初始化 scraper，daemon 线程启动 Flask，创建 pywebview 窗口
app.py              → Flask 后端：路由 + 异步工作线程（asyncio 事件循环独立于 Flask 线程）
scraper.py          → DeepSeekScraper：Playwright 浏览器管理、登录流程、API 调用
daily_tracker.py    → 每日用量快照：计算当日增量、7 天历史、自动清理 >30 天旧数据
float_ball.py       → tkinter 悬浮球（独立进程）：无边框圆形窗口，双击恢复主窗口
static/app.js       → 前端仪表盘：登录流程、余额告警、Chart.js 图表渲染
static/style.css    → 样式
templates/index.html → Jinja2 仪表盘页面
data/               → 运行时数据（browser_state/、daily_snapshots.json）
```

## 架构要点

### 异步模型 (app.py)
Flask 默认多线程处理请求，但 Playwright 要求所有操作在同一事件循环上执行。解决方案：
- 启动一个 daemon 线程运行独立的 `asyncio.run_forever()` 事件循环
- 所有 Playwright 操作通过 `_run_async()` → `asyncio.run_coroutine_threadsafe()` 调度到该循环
- 超时 60 秒

### 认证机制 (scraper.py)
- 使用 Playwright **持久化浏览器上下文** (`launch_persistent_context`)，登录态跨会话保留
- 浏览器状态存储在 `data/browser_state/`
- 从 `localStorage.userToken` 提取 token，作为 Bearer token 调用 DeepSeek 内部 API
- Token 过期（API 返回 code=40002）自动刷新

### 反检测 (scraper.py)
- 注入 `ANTI_DETECTION_SCRIPT` 隐藏 `navigator.webdriver`
- 伪造 `chrome.runtime`、`navigator.plugins`、`navigator.languages`
- 自定义 User-Agent 模拟 Chrome 131
- 启动参数 `--disable-blink-features=AutomationControlled`

### 折叠/展开 (app.py + float_ball.py)
- 关闭主窗口 → 隐藏 pywebview 窗口，subprocess 启动 `float_ball.py`
- 双击悬浮球 → HTTP GET `/api/expand` → terminate 悬浮球进程，show 主窗口
- 悬浮球用 tkinter `overrideredirect` 无边框 + `transparentcolor` 实现圆形
- 余额 < 5 元时边框变黄告警

### 每日追踪 (daily_tracker.py)
- 每次 fetch dashboard 时调用 `take_snapshot()` 记录当前累计值
- 当日首次快照 = baseline，后续快照 = last
- 当日增量 = last - baseline，7 天柱状图同理
- 自动清理 >30 天旧数据

### 开机自启 (app.py)
- `/api/autostart/enable` 通过 PowerShell 创建 `.lnk` 快捷方式到 Windows Startup 文件夹
- 使用 `pythonw.exe`（无控制台窗口） + `desktop.py --folded`

## 代码规范

- Python 文件用 4 空格缩进，注释用中文
- 日志统一用 `logging.getLogger(__name__)`
- Flask 路由返回 `jsonify(...)`，前端用 `fetch()` 调用
- 异步操作只在 scraper 中，Flask 路由层全是同步代码（通过 `_run_async` 桥接）
- 全局单例 `get_scraper()` 管理唯一的 `DeepSeekScraper` 实例
