# DeepSeek 平台监控

桌面应用，抓取 [DeepSeek 开放平台](https://platform.deepseek.com) 的用量数据，实时展示余额、Token 用量、缓存命中率和各模型费用。支持折叠为迷你悬浮球。

## 功能

- 📊 仪表盘：账户余额、7 天用量柱状图、各模型 Token 消耗
- 💰 费用追踪：按模型统计费用，支持缓存命中率展示
- 🫧 悬浮球：折叠后显示当日输入/输出 Token 数，双击恢复主窗口
- 🔄 自动刷新：每 60 秒更新数据
- 📈 每日统计：记录每日增量用量，保留 7 天历史

## 环境要求

- Python 3.8+
- Chromium 浏览器（二选一）：
  - **方案 A（推荐）**：使用系统已安装的 Chrome/Edge，无需下载
  - **方案 B**：Playwright Chromium（需下载 ~150MB）

## 安装

```bash
git clone https://github.com/Hyihhhh/DeepSeek_Monitor.git
cd DeepSeek_Monitor
pip install -r requirements.txt
```

### 浏览器配置

**方案 A：使用系统浏览器（跳过下载，国内首选）**

设置环境变量指向你电脑上的 Chrome 或 Edge：

```bash
# Windows PowerShell
$env:CHROMIUM_PATH = "C:\Program Files\Google\Chrome\Application\chrome.exe"

# Windows CMD
set CHROMIUM_PATH=C:\Program Files\Google\Chrome\Application\chrome.exe
```

或者 Edge：
```
C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe
```

**方案 B：安装 Playwright Chromium（走国内镜像加速）**

```bash
# Windows CMD
set PLAYWRIGHT_DOWNLOAD_HOST=https://npmmirror.com/mirrors/playwright/
playwright install chromium

# Windows PowerShell
$env:PLAYWRIGHT_DOWNLOAD_HOST = "https://npmmirror.com/mirrors/playwright/"
playwright install chromium
```

## 使用

```bash
# 启动桌面应用（推荐）
python desktop.py

# 仅启动 Web 服务（开发调试）
python app.py
# 然后打开 http://localhost:5000

# 单独运行悬浮球
python float_ball.py
```

首次启动需要登录 DeepSeek 账号，登录态会通过持久化浏览器上下文保留。

## 项目结构

```
desktop.py          → 入口：预初始化 scraper，daemon 线程启动 Flask，创建 pywebview 窗口
app.py              → Flask 后端，独立 asyncio 工作线程处理 Playwright 操作
scraper.py          → DeepSeekScraper：登录、Token 提取、API 调用
daily_tracker.py    → 用量快照存储，计算当日增量与 7 天历史
float_ball.py       → tkinter 悬浮球窗口（无边框圆形）
static/app.js       → 前端仪表盘：登录流程、余额告警、图表渲染
static/style.css    → 样式
templates/index.html → 仪表盘页面
```

## 折叠/展开

关闭主窗口 → 自动折叠为悬浮球  
双击悬浮球 → 恢复主窗口
