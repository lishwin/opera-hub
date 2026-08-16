"""可选的浏览器抓取（Playwright）。

大都会歌剧院、芝加哥抒情歌剧院、巴伐利亚国家歌剧院等站点有 Cloudflare
反爬或纯 JS 渲染，普通请求拿不到数据。启用方式：

1. 安装额外依赖：pip install -r requirements-browser.txt
2. 安装 Chromium：python -m playwright install chromium
3. 设置环境变量 OP_HUB_ENABLE_BROWSER=1

未启用时，这些剧院的排期会自动跳过，不影响其他数据源。
"""
import os

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def available() -> bool:
    if os.environ.get("OP_HUB_ENABLE_BROWSER") != "1":
        return False
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def fetch_json(urls: list[str], warmup_url: str) -> list:
    """先访问 warmup_url 通过反爬校验，再从页面上下文请求 JSON。

    每个 URL 使用全新的浏览器上下文：Cloudflare 发放的放行 cookie
    通常只够一次同源请求使用，新上下文能保证每次请求都干净放行。
    """
    from playwright.sync_api import sync_playwright

    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            for url in urls:
                results.append(_cleared_json(browser, warmup_url, url))
        finally:
            browser.close()
    return results


def _cleared_json(browser, warmup_url: str, api_url: str):
    last_status = 0
    for _ in range(4):
        ctx = browser.new_context(user_agent=BROWSER_UA)
        try:
            page = ctx.new_page()
            page.goto(warmup_url, wait_until="domcontentloaded", timeout=60_000)
            result = page.evaluate(
                """async (url) => {
                    const r = await fetch(url, { headers: { Accept: 'application/json' } });
                    return { ok: r.ok, status: r.status, body: r.ok ? await r.json() : null };
                }""",
                api_url,
            )
            if result.get("ok"):
                return result["body"]
            last_status = result.get("status", 0)
        finally:
            ctx.close()
    raise RuntimeError(f"浏览器 JSON 抓取失败，最后状态码 {last_status}")


def fetch_html(url: str, wait_selector: str | None = None, timeout: int = 45_000, scroll: int = 0) -> str:
    """渲染页面并返回完整 HTML。

    scroll 参数用于懒加载页面：加载完成后向下滚动若干次，触发更多内容。
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            ctx = browser.new_context(user_agent=BROWSER_UA)
            page = ctx.new_page()
            page.goto(url, wait_until="domcontentloaded", timeout=60_000)
            if wait_selector:
                page.wait_for_selector(wait_selector, state="attached", timeout=timeout)
            for _ in range(scroll):
                page.mouse.wheel(0, 8000)
                page.wait_for_timeout(1500)
            if wait_selector:
                page.wait_for_selector(wait_selector, state="visible", timeout=timeout)
            return page.content()
        finally:
            browser.close()
