"""
DeepSeek Platform Monitor - Desktop App (Single Window)

Single window with two modes:
  - Expanded: 720x820 full dashboard
  - Folded:   100x120 mini ball at screen right edge

No second window → no rectangular border issue.
"""
import sys
import threading
import time
import logging
import asyncio
import argparse
import webview

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("desktop")

from scraper import get_scraper

def pre_init():
    scraper = get_scraper()
    loop = asyncio.new_event_loop()
    try:
        logger.info("Pre-initializing browser context...")
        loop.run_until_complete(scraper.check_login())
        logger.info(f"Pre-init done. Logged in: {scraper._login_state == 'logged_in'}")
    except Exception as e:
        logger.warning(f"Pre-init failed (non-fatal): {e}")
    finally:
        loop.close()

pre_init()

from app import app

# Window reference
_main_win = None

def start_flask():
    app.run(host="127.0.0.1", port=5000, debug=False, use_reloader=False)

def get_screen_size():
    """Get primary monitor work area."""
    try:
        for m in get_monitors():
            if m.is_primary:
                return m.width, m.height
    except:
        pass
    return 1920, 1080

def main(folded=False):
    global _main_win
    screen_w, screen_h = get_screen_size()

    flask_thread = threading.Thread(target=start_flask, daemon=True)
    flask_thread.start()
    time.sleep(2)

    _main_win = webview.create_window(
        title="DeepSeek 平台监控",
        url="http://127.0.0.1:5000",
        width=720, height=820,
        resizable=True, on_top=False, confirm_close=False,
    )

    import app as app_module
    app_module._windows = {"main": _main_win}

    # Close button → fold to float ball
    def on_closing():
        try: app_module.fold_window()
        except: pass
        return False
    _main_win.events.closing += on_closing

    # Start in folded mode if --folded was passed
    def _auto_fold():
        if folded:
            time.sleep(3)  # Wait for Flask + page to load
            try:
                app_module.fold_window()
            except Exception as e:
                logger.warning(f"Auto-fold failed: {e}")

    threading.Thread(target=_auto_fold, daemon=True).start()

    # Retry webview.start() — Edge WebView2 may not be ready at boot time
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"Starting webview (attempt {attempt}/{max_retries})...")
            webview.start(gui="edgechromium", debug=False)
            break
        except Exception as e:
            logger.error(f"Webview start failed: {e}")
            if attempt < max_retries:
                logger.info(f"Retrying in 3 seconds...")
                time.sleep(3)
            else:
                logger.error("Webview failed after all retries. Flask is still running.")
                # Keep Flask alive so float ball can fetch data
                while True:
                    time.sleep(60)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--folded", action="store_true", help="Start folded into float ball")
    args = parser.parse_args()
    main(folded=args.folded)
