"""艺术家关注名单的动态扫描与档案更新。"""
from . import store


def _matched(text: str, keywords: list[str]) -> bool:
    low = text.lower()
    return any(k and k.lower() in low for k in keywords)


def scan(watchlist: list[dict], news_items: list[dict], performances: list[dict]) -> dict:
    """扫描新闻与排期，返回 {artist_id: [mention, ...]}。"""
    result = {}
    for artist in watchlist:
        keywords = (
            [artist.get("name", "")]
            + artist.get("name_en", [])
            + artist.get("keywords", [])
        )
        mentions = []
        for item in news_items:
            text = f'{item.get("title", "")} {item.get("summary", "")}'
            if _matched(text, keywords):
                mentions.append(
                    {
                        "type": "新闻",
                        "title": item.get("title", ""),
                        "url": item.get("url", ""),
                        "date": item.get("published") or item.get("fetched_at", ""),
                    }
                )
        for perf in performances:
            cast = perf.get("cast") or []
            if isinstance(cast, dict):
                cast = list(cast.values())
            cast_text = " ".join(str(c) for c in cast)
            text = (
                f'{perf.get("composer", "")} {perf.get("title", "")} '
                f'{perf.get("house_name", "")} {perf.get("conductor", "")} {cast_text}'
            )
            if _matched(text, keywords):
                mentions.append(
                    {
                        "type": "演出",
                        "title": perf.get("title", ""),
                        "url": perf.get("url", ""),
                        "date": perf.get("date", ""),
                    }
                )
        if mentions:
            result[artist["id"]] = mentions
    return result


def merge_watchlist(artists_json: list[dict], mentions: dict) -> list[dict]:
    """把新扫描到的动态并入 data/artists.json，按 URL 去重，每人保留最近 30 条。"""
    now = store.utc_now_iso()
    by_id = {a["id"]: a for a in artists_json}
    for artist_id, new_mentions in mentions.items():
        entry = by_id.setdefault(artist_id, {"id": artist_id})
        old = entry.get("mentions", [])
        seen_urls = {m.get("url") for m in old}
        merged = list(old)
        for m in new_mentions:
            if m.get("url") not in seen_urls:
                merged.append(m)
                seen_urls.add(m.get("url"))
        entry["mentions"] = merged[-30:]
        entry["last_updated"] = now
    return list(by_id.values())
