"""从新闻源的 RSS/Atom 订阅抓取最新报道。"""
import calendar
import time
from datetime import datetime, timezone

import feedparser

from . import fetch, store


def _to_iso(struct_time) -> str | None:
    if not struct_time:
        return None
    try:
        epoch = calendar.timegm(struct_time)
        return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat(timespec="seconds")
    except Exception:
        return None


def fetch_source(source: dict) -> list[dict]:
    """抓取单个新闻源，返回标准化条目列表。"""
    if not source.get("enabled", True):
        return []
    url = source.get("url", "")
    if not url:
        return []
    text = fetch.fetch_text(url, timeout=45)
    parsed = feedparser.parse(text)
    items = []
    for entry in parsed.entries[:30]:
        link = entry.get("link") or entry.get("id") or ""
        title = (entry.get("title") or "").strip()
        if not title or not link:
            continue
        summary = entry.get("summary") or entry.get("description") or ""
        items.append(
            {
                "id": f'{source["id"]}:{link}',
                "source": source["id"],
                "source_name": source.get("name", source["id"]),
                "title": title,
                "url": link,
                "summary": summary[:400],
                "published": _to_iso(entry.get("published_parsed") or entry.get("updated_parsed")),
                "fetched_at": store.utc_now_iso(),
            }
        )
    return items


def fetch_all(news_cfg: dict) -> list[dict]:
    """抓取所有启用的新闻源，单个源失败不影响整体。"""
    items = []
    for source in news_cfg.get("sources", []):
        try:
            items.extend(fetch_source(source))
        except Exception as exc:
            print(f"[warn] 新闻源抓取失败 {source.get('id')}: {exc}")
    return items


def filter_by_keywords(items: list[dict], keywords: list[str]) -> list[dict]:
    """只保留与歌剧、关注剧院和艺术家相关的条目，减少噪音。"""
    kw = [k.lower() for k in keywords if k]
    if not kw:
        return items
    out = []
    for item in items:
        text = f'{item["title"]} {item.get("summary", "")}'.lower()
        if any(k in text for k in kw):
            out.append(item)
    return out
