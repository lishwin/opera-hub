"""通用的网络抓取小工具，只依赖标准库。"""
import gzip
import json
import ssl
import time
import urllib.request
import urllib.error
from io import BytesIO

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
)


def _urlopen_with_retry(req, timeout: int, context=None, tries: int = 5):
    last = None
    for i in range(tries):
        try:
            return urllib.request.urlopen(req, timeout=timeout, context=context)
        except urllib.error.HTTPError as exc:
            if exc.code < 500:
                raise
            last = exc
        except Exception as exc:
            last = exc
        if i < tries - 1:
            time.sleep(2 * (i + 1))
    raise last


def fetch_bytes(url: str, timeout: int = 30, headers: dict | None = None, context=None) -> bytes:
    hdrs = {
        "User-Agent": USER_AGENT,
        "Accept": "*/*",
        "Accept-Encoding": "gzip",
    }
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(
        url,
        headers=hdrs,
    )
    with _urlopen_with_retry(req, timeout, context) as resp:
        raw = resp.read()
        if resp.headers.get("Content-Encoding", "").lower() == "gzip":
            raw = gzip.GzipFile(fileobj=BytesIO(raw)).read()
        return raw


def fetch_text(url: str, timeout: int = 30, headers: dict | None = None, context=None) -> str:
    raw = fetch_bytes(url, timeout, headers=headers, context=context)
    for enc in ("utf-8", "utf-8-sig", "gb18030", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def fetch_json(url: str, timeout: int = 30, headers: dict | None = None, context=None):
    return json.loads(fetch_text(url, timeout, headers=headers, context=context))


def fetch_json_post(url: str, payload: dict, timeout: int = 60):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with _urlopen_with_retry(req, timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))
