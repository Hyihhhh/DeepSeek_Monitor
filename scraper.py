"""
DeepSeek platform data scraper using internal API endpoints.

Authentication: extracts userToken from localStorage (set after login),
then uses it as Bearer token in Authorization header for API calls.
"""
import asyncio
import json
import os
import time
import logging
from datetime import datetime
from playwright.async_api import async_playwright
import httpx

logger = logging.getLogger(__name__)

USER_DATA_DIR = os.path.join(os.path.dirname(__file__), "data", "browser_state")
CHROMIUM_PATH = os.environ.get("CHROMIUM_PATH")  # 可选：自定义浏览器路径，跳过 playwright install
HEADED_MODE = os.environ.get("DEEPSEEK_HEADED", "").lower() in ("1", "true", "yes")  # 有头模式

# 注入脚本：隐藏 webdriver 特征，防止被检测为机器人
ANTI_DETECTION_SCRIPT = """
// 移除 navigator.webdriver 标记
Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
// 伪造 chrome.runtime
window.chrome = { runtime: {} };
// 伪造权限查询
const originalQuery = window.navigator.permissions.query;
window.navigator.permissions.query = (parameters) => (
    parameters.name === 'notifications' ?
    Promise.resolve({ state: Notification.permission }) :
    originalQuery(parameters)
);
// 覆盖 plugins 和 languages
Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });
"""

API_BASE = "https://platform.deepseek.com"
ENDPOINTS = {
    "user_summary": "/api/v0/users/get_user_summary",
    "usage_amount": "/api/v0/usage/amount",
    "usage_cost": "/api/v0/usage/cost",
    "user_info": "/auth-api/v0/users/current",
}


class DeepSeekScraper:
    """Manages Playwright browser and data extraction from DeepSeek platform."""

    def __init__(self):
        self._playwright = None
        self._context = None
        self._page = None
        self._cookies = {}
        self._auth_token = None
        self._login_state = "unknown"
        self._phone = "18420045098"
        self._cached_data = {}
        self._last_fetch = 0
        self._user_name = ""
        self._init_lock = asyncio.Lock()

    async def _ensure_browser(self):
        """Ensure browser context is initialized. Thread-safe via asyncio lock."""
        if self._context is not None:
            return

        async with self._init_lock:
            if self._context is not None:
                return

            os.makedirs(USER_DATA_DIR, exist_ok=True)
            self._playwright = await async_playwright().start()
            launch_args = {
                "user_data_dir": USER_DATA_DIR,
                "headless": not HEADED_MODE,
                "viewport": {"width": 1400, "height": 900},
                "args": [
                    "--disable-blink-features=AutomationControlled",
                    "--disable-dev-shm-usage",
                ],
                "user_agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/131.0.0.0 Safari/537.36"
                ),
            }
            if CHROMIUM_PATH:
                launch_args["executable_path"] = CHROMIUM_PATH
                logger.info(f"Using custom browser: {CHROMIUM_PATH}")
            self._context = await self._playwright.chromium.launch_persistent_context(**launch_args)
            # 注入反检测脚本，对新页面自动生效
            await self._context.add_init_script(ANTI_DETECTION_SCRIPT)
            self._page = await self._context.new_page()
            await self._extract_auth()

    async def _extract_auth(self):
        """Navigate to platform and extract auth token from localStorage."""
        for attempt in range(3):
            try:
                await self._page.goto(
                    "https://platform.deepseek.com/usage",
                    wait_until="domcontentloaded",
                    timeout=20000,
                )
                await self._page.wait_for_timeout(3000)

                current_url = self._page.url

                if "login" in current_url.lower() or "auth" in current_url.lower():
                    self._login_state = "need_login"
                    logger.info("Not logged in - redirected to login page")
                    return

                # Extract token from localStorage
                try:
                    token_data = await self._page.evaluate(
                        "() => localStorage.getItem('userToken')"
                    )
                    if token_data:
                        parsed = json.loads(token_data)
                        self._auth_token = parsed.get("value", "")
                except Exception as e:
                    logger.warning(f"Failed to extract token: {e}")

                # Refresh cookies
                raw_cookies = await self._context.cookies()
                self._cookies = {c["name"]: c["value"] for c in raw_cookies}

                if self._auth_token:
                    self._login_state = "logged_in"
                else:
                    self._login_state = "need_login"
                return

            except Exception as e:
                logger.warning(f"_extract_auth attempt {attempt+1} failed: {e}")
                if attempt < 2:
                    await asyncio.sleep(2)

        self._login_state = "need_login"

    async def _api_request(self, path, params=None):
        """Make an authenticated API request to the DeepSeek platform."""
        await self._ensure_browser()

        if not self._auth_token:
            return None

        url = API_BASE + path
        if params:
            qs = "&".join(f"{k}={v}" for k, v in params.items())
            url += "?" + qs

        headers = {
            "Accept": "application/json",
            "Authorization": f"Bearer {self._auth_token}",
            "Referer": "https://platform.deepseek.com/usage",
        }

        for attempt in range(3):
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    resp = await client.get(url, cookies=self._cookies, headers=headers)
                    if resp.status_code == 200:
                        data = resp.json()
                        if data.get("code") == 0:
                            return data
                        if data.get("code") == 40002:  # Token expired
                            logger.info("Token expired, refreshing...")
                            await self._extract_auth()
                            if self._auth_token:
                                headers["Authorization"] = f"Bearer {self._auth_token}"
                                continue
                            self._login_state = "need_login"
                            return None
                    elif resp.status_code == 401:
                        self._login_state = "need_login"
                        return None
                    return None
            except Exception as e:
                logger.warning(f"API {path} attempt {attempt+1}: {e}")
                if attempt < 2:
                    await asyncio.sleep(1)
        return None

    async def check_login(self):
        """Check if currently logged in."""
        await self._ensure_browser()

        if self._login_state == "logged_in" and self._auth_token:
            user_info = await self._api_request(ENDPOINTS["user_info"])
            if user_info and user_info.get("code") == 0:
                profile = user_info["data"]["biz_data"].get("id_profile", {})
                self._user_name = profile.get("name", "")
            return {
                "logged_in": True,
                "user_name": self._user_name,
                "mobile": self._phone,
            }

        if self._login_state != "logged_in":
            await self._extract_auth()

        if self._login_state == "logged_in" and self._auth_token:
            return {"logged_in": True, "user_name": self._user_name, "mobile": self._phone}
        return {"logged_in": False}

    async def send_code(self, phone=None):
        """Send SMS verification code to phone number."""
        if phone:
            self._phone = phone
        await self._ensure_browser()

        try:
            await self._page.goto(
                "https://platform.deepseek.com",
                wait_until="domcontentloaded",
                timeout=20000,
            )
            await self._page.wait_for_timeout(2000)

            current_url = self._page.url
            if "/usage" in current_url or "/api_keys" in current_url:
                await self._extract_auth()
                return {"success": True, "message": "已登录，无需验证码", "already_logged_in": True}

            phone_input = await self._page.query_selector(
                'input[type="tel"], input[placeholder*="手机"], '
                'input[placeholder*="phone"], input[name="phone"]'
            )
            if not phone_input:
                phone_tab = await self._page.query_selector(
                    'text=手机登录, text=手机号登录, text=短信登录'
                )
                if phone_tab:
                    await phone_tab.click()
                    await self._page.wait_for_timeout(1000)
                phone_input = await self._page.query_selector(
                    'input[type="tel"], input[placeholder*="手机"], '
                    'input[placeholder*="phone"], input[name="phone"]'
                )

            if not phone_input:
                return {"success": False, "message": "找不到手机号输入框"}

            await phone_input.click()
            await phone_input.fill(self._phone)
            await self._page.wait_for_timeout(500)

            send_btn = await self._page.query_selector(
                'button:has-text("发送"), button:has-text("获取验证码"), '
                'button:has-text("验证码"), span:has-text("发送")'
            )
            if send_btn:
                await send_btn.click()
                self._login_state = "waiting_code"
                return {"success": True, "message": "验证码已发送", "already_logged_in": False}
            else:
                return {"success": False, "message": "找不到发送按钮"}

        except Exception as e:
            logger.error(f"send_code error: {e}")
            return {"success": False, "message": str(e)}

    async def verify_code(self, code):
        """Submit SMS verification code to complete login."""
        await self._ensure_browser()

        try:
            await self._page.goto(
                "https://platform.deepseek.com",
                wait_until="domcontentloaded",
                timeout=20000,
            )
            await self._page.wait_for_timeout(2000)

            current_url = self._page.url
            if "/usage" in current_url or "/api_keys" in current_url:
                await self._extract_auth()
                return {"success": True, "message": "已处于登录状态"}

            code_input = await self._page.query_selector(
                'input[type="text"][maxlength="6"], '
                'input[placeholder*="验证码"], input[placeholder*="code"]'
            )
            if not code_input:
                code_input = await self._page.query_selector('input[type="number"]')

            if not code_input:
                return {"success": False, "message": "找不到验证码输入框"}

            await code_input.click()
            await code_input.fill(code)
            await self._page.wait_for_timeout(500)

            submit_btn = await self._page.query_selector(
                'button:has-text("登录"), button:has-text("确认"), button[type="submit"]'
            )
            if submit_btn:
                await submit_btn.click()
                await self._page.wait_for_timeout(6000)

                current_url = self._page.url
                if "/usage" in current_url or "/api_keys" in current_url:
                    await self._extract_auth()
                    return {"success": True, "message": "登录成功"}
                else:
                    return {"success": False, "message": "登录失败，请检查验证码"}

            return {"success": False, "message": "找不到提交按钮"}

        except Exception as e:
            logger.error(f"verify_code error: {e}")
            return {"success": False, "message": str(e)}

    async def fetch_dashboard(self):
        """Fetch all dashboard data from DeepSeek platform."""
        now = datetime.now()
        result = {
            "timestamp": now.isoformat(),
            "balance": {},
            "models": [],
            "usage": {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "cache_hit_rate": 0,
            },
            "cost": {"monthly": "0", "balance": "0", "bonus_balance": "0"},
        }

        # 1. User summary
        summary = await self._api_request(ENDPOINTS["user_summary"])
        if summary and summary.get("code") == 0:
            biz = summary["data"]["biz_data"]
            nw = biz.get("normal_wallets", [])
            bw = biz.get("bonus_wallets", [])
            mc = biz.get("monthly_costs", [])

            result["balance"] = {
                "normal": nw[0]["balance"] if nw else "0",
                "bonus": bw[0]["balance"] if bw else "0",
                "token_estimation": biz.get("total_available_token_estimation", "0"),
            }
            result["cost"]["balance"] = result["balance"]["normal"]
            result["cost"]["bonus_balance"] = result["balance"]["bonus"]
            result["cost"]["monthly"] = mc[0]["amount"] if mc else "0"
            result["usage"]["total_tokens"] = int(biz.get("monthly_token_usage", "0"))

        # 2. Usage amount by model
        amount = await self._api_request(ENDPOINTS["usage_amount"], {
            "month": str(now.month), "year": str(now.year),
        })
        if amount and amount.get("code") == 0:
            models_data = amount["data"]["biz_data"].get("total", [])
            for m in models_data:
                mi = {"name": m["model"], "usage": {}}
                total_tokens = 0
                for u in m.get("usage", []):
                    token_type = u["type"]
                    token_amount = int(u.get("amount", "0"))
                    mi["usage"][token_type] = token_amount
                    total_tokens += token_amount
                mi["total_tokens"] = total_tokens

                # Per-model cache hit rate
                hit = mi["usage"].get("PROMPT_CACHE_HIT_TOKEN", 0)
                miss = mi["usage"].get("PROMPT_CACHE_MISS_TOKEN", 0)
                prompt = mi["usage"].get("PROMPT_TOKEN", 0)
                total = hit + miss + prompt
                mi["cache_hit_rate"] = round(hit / total * 100, 1) if total > 0 else 0

                result["models"].append(mi)

                if "PROMPT_TOKEN" in mi["usage"]:
                    result["usage"]["input_tokens"] += mi["usage"]["PROMPT_TOKEN"]
                if "PROMPT_CACHE_MISS_TOKEN" in mi["usage"]:
                    result["usage"]["input_tokens"] += mi["usage"]["PROMPT_CACHE_MISS_TOKEN"]
                if "PROMPT_CACHE_HIT_TOKEN" in mi["usage"]:
                    result["usage"]["input_tokens"] += mi["usage"]["PROMPT_CACHE_HIT_TOKEN"]
                if "RESPONSE_TOKEN" in mi["usage"]:
                    result["usage"]["output_tokens"] += mi["usage"]["RESPONSE_TOKEN"]

            # Overall cache hit rate
            total_hit = sum(m["usage"].get("PROMPT_CACHE_HIT_TOKEN", 0) for m in result["models"])
            total_miss = sum(m["usage"].get("PROMPT_CACHE_MISS_TOKEN", 0) for m in result["models"])
            total_prompt = sum(m["usage"].get("PROMPT_TOKEN", 0) for m in result["models"])
            overall = total_hit + total_miss + total_prompt
            result["usage"]["cache_hit_rate"] = round(total_hit / overall * 100, 1) if overall > 0 else 0

        # 3. Usage cost by model
        cost = await self._api_request(ENDPOINTS["usage_cost"], {
            "month": str(now.month), "year": str(now.year),
        })
        if cost and cost.get("code") == 0:
            cost_data = cost["data"]["biz_data"]
            if isinstance(cost_data, list):
                for entry in cost_data:
                    for m in entry.get("total", []):
                        mn = m["model"]
                        mc = sum(float(u.get("amount", "0")) for u in m.get("usage", []))
                        for mi in result["models"]:
                            if mi["name"] == mn:
                                mi["cost"] = round(mc, 4)
                                break

        # 4. Daily tracking
        from daily_tracker import take_snapshot
        daily = take_snapshot({
            "total_tokens": result["usage"]["total_tokens"],
            "input_tokens": result["usage"]["input_tokens"],
            "output_tokens": result["usage"]["output_tokens"],
            "monthly_cost": result["cost"]["monthly"],
        })
        result["daily"] = daily

        self._last_fetch = time.time()
        self._cached_data = result
        return result

    async def close(self):
        if self._page:
            await self._page.close()
            self._page = None
        if self._context:
            await self._context.close()
            self._context = None
        if self._playwright:
            await self._playwright.stop()
            self._playwright = None


_scraper = None


def get_scraper():
    global _scraper
    if _scraper is None:
        _scraper = DeepSeekScraper()
    return _scraper
