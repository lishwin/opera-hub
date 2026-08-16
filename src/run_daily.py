"""每日运行入口：采集 → 整理 → 写文件 → 推送。

用法：
  python src/run_daily.py              # 更新并推送
  python src/run_daily.py --no-notify  # 只整理不推送
"""
import argparse
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src import (
    artists as artist_mod,
    config,
    digest as digest_mod,
    houses,
    ncpa as ncpa_mod,
    notify,
    rss_news,
    store,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="世界歌剧院动态采集")
    parser.add_argument("--since-hours", type=int, default=24, help="新闻时间范围（小时）")
    parser.add_argument("--no-notify", action="store_true", help="跳过推送")
    args = parser.parse_args()

    state = store.load_json(config.DATA_DIR / "state.json", {})
    seen = set(state.get("seen_news", []))
    today = store.beijing_date()
    today_iso = today.isoformat()

    # 1. 新闻
    news_cfg = config.news_config()
    fetched = rss_news.fetch_all(news_cfg)
    kept = [item for item in fetched if item["url"] not in seen]
    seen.update(item["url"] for item in kept)
    new_items = rss_news.filter_by_keywords(kept, news_cfg.get("filter_keywords", []))
    news_json = store.load_json(config.DATA_DIR / "news.json", [])
    existing_urls = {n["url"] for n in news_json}
    for item in new_items:
        if item["url"] not in existing_urls:
            news_json.append(item)
            existing_urls.add(item["url"])
    news_json = sorted(
        news_json,
        key=lambda n: n.get("published") or n.get("fetched_at") or "",
        reverse=True,
    )[:300]
    store.save_json(config.DATA_DIR / "news.json", news_json)

    # 2. 排期（歌剧院订阅源）
    # 排期每天全量刷新，避免残留已过期或已变更的场次
    by_id = {}
    for house in config.houses_config():
        for item in houses.fetch_house(house):
            by_id[item["id"]] = item
    performances = sorted(
        (p for p in by_id.values() if p.get("date", "") >= today_iso),
        key=lambda p: p.get("date", "9999-99-99"),
    )
    store.save_json(config.DATA_DIR / "performances.json", performances)

    # 3. 艺术家动态
    watchlist = config.artists_config()
    watchlist_by_id = {a["id"]: a for a in watchlist}
    artists_json = store.load_json(config.DATA_DIR / "artists.json", [])
    mentions = artist_mod.scan(watchlist, new_items, performances)
    artists_json = artist_mod.merge_watchlist(artists_json, mentions)
    store.save_json(config.DATA_DIR / "artists.json", artists_json)

    # 4. 日报
    ncpa_index = ncpa_mod.load_index()
    ncpa_artists = [
        {
            "name": a["name"],
            "category": a.get("category", ""),
            "name_en": a.get("name_en", []),
            "productions": [
                {
                    "year": ncpa_index.productions[pid].get("year"),
                    "title": ncpa_index.productions[pid].get("title"),
                    "composer": ncpa_index.productions[pid].get("composer", ""),
                }
                for pid in a["prod_ids"]
            ],
        }
        for a in ncpa_index.artists.values()
    ]
    ncpa_artists.sort(key=lambda x: (-len(x["productions"]), x["name"]))
    store.save_json(config.DATA_DIR / "ncpa_artists.json", ncpa_artists)
    digest = digest_mod.build(
        new_items,
        performances,
        mentions,
        watchlist_by_id,
        today=today,
        ncpa_index=ncpa_index,
    )
    store.save_json(config.DATA_DIR / "digest" / "latest.json", digest)
    md = digest_mod.to_markdown(digest)
    (config.DATA_DIR / "digest" / f"{today_iso}.md").write_text(md, encoding="utf-8")
    (config.DATA_DIR / "digest" / "latest.md").write_text(md, encoding="utf-8")

    # 5. 看板数据摘要
    horizon = (today + timedelta(days=30)).isoformat()
    upcoming_30 = [p for p in performances if p.get("date") and today_iso <= p["date"] <= horizon][:80]
    store.save_json(
        config.DATA_DIR / "summary.json",
        {
            "updated_at": store.utc_now_iso(),
            "stats": {
                "houses": len(config.houses_config()),
                "performances": len(performances),
                "news": len(news_json),
                "artists": len(artists_json),
                "ncpa_artists": len(ncpa_index.artists),
                "ncpa_productions": len(ncpa_index.productions),
            },
            "upcoming_30": [
                {
                    "date": p["date"],
                    "house": p.get("house_name", ""),
                    "title": f'{p.get("composer", "")} {p.get("title", "")}'.strip(),
                    "url": p.get("url", ""),
                }
                for p in upcoming_30
            ],
        },
    )

    # 6. 状态与推送
    state["seen_news"] = sorted(seen)[-2000:]
    state["last_run"] = store.utc_now_iso()
    store.save_json(config.DATA_DIR / "state.json", state)

    if not args.no_notify:
        channel = notify.send(md, f"歌剧日报 {today_iso}")
        print(f"[info] 推送渠道: {channel}")
    print(f"[done] 新闻 {len(new_items)} 条 / 排期 {len(performances)} 条 / 艺术家 {len(artists_json)} 人")

    if not performances:
        print("[hint] 目前还没有演出排期数据：请在 config/houses.json 的 feeds 中填写歌剧院订阅链接。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
