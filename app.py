"""
DeepSeek Platform Monitor - Flask Backend

Uses a dedicated worker thread with its own asyncio event loop
for all Playwright/async operations, avoiding event-loop conflicts
with Flask's multi-threaded request handling.
"""
import asyncio
import logging
import os
import sys
import threading
from concurrent.futures import Future
from flask import Flask, jsonify, request, render_template
from scraper import get_scraper

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True

# Set by desktop.py after creating windows
_windows = {}
_screen_w = 1920
_screen_h = 1080

_is_folded = False
_float_process = None


def fold_window():
    """Hide dashboard, launch transparent tkinter float ball."""
    global _is_folded, _float_process
    win = _windows.get("main")
    if not win: return
    try:
        win.hide()
    except Exception as e:
        logger.error(f"fold hide error: {e}")

    # Launch tkinter float ball subprocess
    if _float_process is None:
        import subprocess, os
        try:
            _float_process = subprocess.Popen(
                [sys.executable, os.path.join(os.path.dirname(__file__), "float_ball.py")],
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == 'win32' else 0,
            )
        except Exception as e:
            logger.error(f"Launch float_ball error: {e}")
    _is_folded = True


def expand_window():
    """Kill float ball, show dashboard."""
    global _is_folded, _float_process
    if _float_process:
        try:
            _float_process.terminate()
            _float_process = None
        except Exception as e:
            logger.error(f"Terminate float error: {e}")

    win = _windows.get("main")
    if not win: return
    try:
        win.show()
    except Exception as e:
        logger.error(f"expand show error: {e}")
    _is_folded = False


# ── Async worker thread ──────────────────────────────────────────────
# Flask serves requests from multiple threads, but Playwright requires
# all operations on a single event loop. We solve this by running a
# dedicated event-loop thread and dispatching all scraper coroutines to it.

_worker_loop = None
_worker_ready = threading.Event()


def _worker_thread():
    """Runs the shared asyncio event loop for all Playwright operations."""
    global _worker_loop
    _worker_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_worker_loop)
    _worker_ready.set()
    _worker_loop.run_forever()


_worker = threading.Thread(target=_worker_thread, daemon=True)
_worker.start()
_worker_ready.wait()


def _run_async(coro):
    """Schedule a coroutine on the worker event loop and block for result."""
    fut = asyncio.run_coroutine_threadsafe(coro, _worker_loop)
    return fut.result(timeout=60)


# ── Routes ───────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/status")
def api_status():
    scraper = get_scraper()
    result = _run_async(scraper.check_login())
    return jsonify(result)


@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json() or {}
    phone = data.get("phone", "18420045098")
    scraper = get_scraper()
    result = _run_async(scraper.send_code(phone))
    return jsonify(result)


@app.route("/api/verify", methods=["POST"])
def api_verify():
    data = request.get_json() or {}
    code = data.get("code", "")
    if not code:
        return jsonify({"success": False, "message": "验证码不能为空"})
    scraper = get_scraper()
    result = _run_async(scraper.verify_code(code))
    return jsonify(result)


@app.route("/api/dashboard")
def api_dashboard():
    scraper = get_scraper()

    status = _run_async(scraper.check_login())
    if not status.get("logged_in"):
        return jsonify({
            "success": False,
            "need_login": True,
            "message": "未登录，请先登录",
            "user": status,
        })

    data = _run_async(scraper.fetch_dashboard())
    if data is None:
        return jsonify({
            "success": False,
            "need_login": True,
            "message": "获取数据失败，可能需要重新登录",
        })

    return jsonify({"success": True, "data": data})


@app.route("/api/fold")
def api_fold():
    """Fold dashboard into mini float ball."""
    fold_window()
    return jsonify({"ok": True, "folded": _is_folded})


@app.route("/api/expand")
def api_expand():
    """Expand mini ball back to full dashboard."""
    expand_window()
    return jsonify({"ok": True, "folded": _is_folded})


@app.route("/api/folded-state")
def api_folded_state():
    """Check if window is currently folded."""
    return jsonify({"folded": _is_folded})


def _startup_folder():
    """Get Windows Startup folder path."""
    return os.path.join(os.environ.get("APPDATA", ""),
                        "Microsoft", "Windows", "Start Menu", "Programs", "Startup")


def _startup_shortcut():
    return os.path.join(_startup_folder(), "DeepSeekMonitor.lnk")


@app.route("/api/autostart/status")
def api_autostart_status():
    """Check if auto-start is enabled."""
    return jsonify({"enabled": os.path.exists(_startup_shortcut())})


@app.route("/api/autostart/enable")
def api_autostart_enable():
    """Enable auto-start by creating a shortcut in Startup folder.

    Creates a shortcut directly to pythonw.exe (the current Python's GUI launcher)
    with desktop.py --folded as arguments. This bypasses the VBS launcher entirely,
    eliminating the hardcoded path fragility and silent-failure problem.
    """
    import subprocess
    project_dir = os.path.dirname(__file__)
    shortcut = _startup_shortcut()

    # Use the pythonw.exe from the same directory as the running Python
    pythonw = sys.executable.replace("python.exe", "pythonw.exe")
    if not os.path.exists(pythonw):
        # Fallback: try shims
        pythonw = os.path.join(
            os.path.dirname(os.path.dirname(sys.executable)),
            "shims", "pythonw.exe",
        )
    desktop_py = os.path.join(project_dir, "desktop.py")

    try:
        os.makedirs(_startup_folder(), exist_ok=True)
        ps = (
            f"$WshShell = New-Object -ComObject WScript.Shell;"
            f"$Shortcut = $WshShell.CreateShortcut('{shortcut}');"
            f"$Shortcut.TargetPath = '{pythonw}';"
            f"$Shortcut.Arguments = '{desktop_py} --folded';"
            f"$Shortcut.WorkingDirectory = '{project_dir}';"
            f"$Shortcut.Save()"
        )
        subprocess.run(["powershell", "-Command", ps], capture_output=True)
        logger.info(f"Auto-start enabled: {pythonw} {desktop_py} --folded")
        return jsonify({"enabled": True, "ok": True})
    except Exception as e:
        return jsonify({"enabled": False, "error": str(e)})


@app.route("/api/autostart/disable")
def api_autostart_disable():
    """Disable auto-start by removing the shortcut."""
    shortcut = _startup_shortcut()
    try:
        if os.path.exists(shortcut):
            os.remove(shortcut)
        return jsonify({"enabled": False, "ok": True})
    except Exception as e:
        return jsonify({"enabled": True, "error": str(e)})


@app.route("/api/refresh", methods=["POST"])
def api_refresh():
    scraper = get_scraper()
    scraper._cached_data = {}
    scraper._last_fetch = 0
    return api_dashboard()


if __name__ == "__main__":
    print("Starting DeepSeek Platform Monitor...")
    print("Open http://localhost:5000 in your browser")
    app.run(host="0.0.0.0", port=5000, debug=True)
