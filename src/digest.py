"""把当天的新闻、排期更新、艺术家动态整理成日报。"""
from datetime import timedelta

from . import store


def _fmt_date(iso: str) -> str:
    return (iso or "")[:10]


def _display(p: dict) -> str:
    composer = p.get("composer") or ""
    title = p.get("title") or ""
    if composer and composer not in title:
        return f"{composer} {title}"
    return title


def build(new_items, performances, artist_mentions, watchlist_by_id, today=None):
    today = today or store.beijing_date()
    today_iso = today.isoformat()
    upcoming = sorted(
        [p for p in performances if p.get("date") and p["date"] >= today_iso],
        key=lambda p: p["date"],
    )[:40]
    upcoming_7 = [p for p in upcoming if p["date"] <= (today + timedelta(days=7)).isoformat()][:15]
    news = [
        {
            "source": n.get("source_name", ""),
            "title": n.get("title", ""),
            "url": n.get("url", ""),
            "date": _fmt_date(n.get("published")),
        }
        for n in sorted(new_items, key=lambda x: x.get("published") or "", reverse=True)[:20]
    ]
    return {
        "date": today_iso,
        "generated_at": store.utc_now_iso(),
        "news": news,
        "schedule_updates": _schedule_updates(performances, today_iso),
        "artists": _artist_section(artist_mentions, watchlist_by_id),
        "upcoming_7": [
            {"date": p["date"], "house": p.get("house_name", ""), "title": _display(p), "url": p.get("url", "")}
            for p in upcoming_7
        ],
    }


def _schedule_updates(performances, today_iso: str) -> list[dict]:
    out = []
    for p in performances:
        if (p.get("updated_at") or "").startswith(today_iso) and p.get("date"):
            out.append({"date": p["date"], "house": p.get("house_name", ""), "title": _display(p), "url": p.get("url", "")})
    return sorted(out, key=lambda x: x["date"])[:15]


def _artist_section(artist_mentions, watchlist_by_id) -> list[dict]:
    out = []
    for artist_id, mentions in artist_mentions.items():
        info = watchlist_by_id.get(artist_id, {})
        out.append(
            {
                "name": info.get("name", artist_id),
                "category": info.get("category", ""),
                "mentions": mentions[-3:],
            }
        )
    return out


def to_markdown(sections: dict) -> str:
    lines = [f"📰 歌剧日报 · {sections['date']}", ""]

    lines.append("▍今日要闻")
    if sections["news"]:
        for n in sections["news"]:
            lines.append(f"- {n['title']} ｜ {n['source']}  {n['url']}")
    else:
        lines.append("今日暂无新报道")
    lines.append("")

    lines.append("▍排期更新")
    if sections["schedule_updates"]:
        for s in sections["schedule_updates"]:
            lines.append(f"- {s['date']} {s['house']}：{s['title']}  {s['url']}")
    else:
        lines.append("今日暂无排期更新")
    lines.append("")

    lines.append("▍艺术家动态")
    if sections["artists"]:
        for a in sections["artists"]:
            suffix = f"（{a['category']}）" if a.get("category") else ""
            lines.append(f"- {a['name']}{suffix}")
            for m in a["mentions"]:
                lines.append(f"  · {m['title']}  {m['url']}")
    else:
        lines.append("关注名单暂无新动态")
    lines.append("")

    lines.append("▍未来 7 天值得关注")
    if sections["upcoming_7"]:
        for u in sections["upcoming_7"]:
            lines.append(f"- {u['date']} {u['house']}：{u['title']}  {u['url']}")
    else:
        lines.append("暂无排期数据")
    return "\n".join(lines)
