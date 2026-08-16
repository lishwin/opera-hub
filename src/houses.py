"""歌剧院排期抓取。

支持的 feed 类型（在 config/houses.json 的 feeds 中配置）：
- ics / json          通用 iCal 与 JSON 订阅（JSON 用 field_map 映射字段）
- roh-json            伦敦皇家歌剧院 JSON:API
- paris-json          巴黎歌剧院节目单 AJAX 接口（分页）
- salzburg-json       萨尔茨堡音乐节 POST JSON 接口
- sfopera-json        旧金山歌剧院 ace-api
- met-json / lyric-json   大都会 / 芝加哥抒情（Cloudflare 保护，需浏览器模式）
- vienna-html         维也纳国家歌剧院月历页
- scala-html          斯卡拉日历页
- zurich-html         苏黎世歌剧节日历（分页）
- sydney-html         悉尼歌剧院 what's on（分页）
- bayreuth-html       拜罗伊特节目页 + 各制作详情页
- bayerische-html     巴伐利亚国家歌剧院（JS 渲染，需浏览器模式）

数据源方法与思路参考了开源项目 Leporello（github.com/philphilphil/leporello-mcp）。
"""
import json
import re
import ssl
import time
from datetime import date, datetime, timedelta
from urllib.parse import urljoin

import icalendar
from bs4 import BeautifulSoup

from . import browser, fetch, store

MONTHS_EN = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]

MONTH_ABBR = {
    "Jan": "01", "Feb": "02", "Mar": "03", "Apr": "04", "May": "05", "Jun": "06",
    "Jul": "07", "Aug": "08", "Sep": "09", "Oct": "10", "Nov": "11", "Dec": "12",
}

FRENCH_MONTHS = {
    "janvier": "01", "janv.": "01", "janv": "01", "jan.": "01", "jan": "01",
    "février": "02", "févr.": "02", "févr": "02", "fév.": "02", "fév": "02",
    "mars": "03", "mar.": "03", "mar": "03",
    "avril": "04", "avr.": "04", "avr": "04",
    "mai": "05",
    "juin": "06",
    "juillet": "07", "juil.": "07", "juil": "07",
    "août": "08",
    "septembre": "09", "sept.": "09", "sept": "09",
    "octobre": "10", "oct.": "10", "oct": "10",
    "novembre": "11", "nov.": "11", "nov": "11",
    "décembre": "12", "déc.": "12", "déc": "12",
}

MONTH_FULL = {
    "january": "01", "february": "02", "march": "03", "april": "04",
    "may": "05", "june": "06", "july": "07", "august": "08",
    "september": "09", "october": "10", "november": "11", "december": "12",
    "juni": "06", "juli": "07", "mai": "05",
}


def _strip_html(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]*>", " ", text or "")).strip()


def _next_months(count: int):
    now = store.beijing_now()
    for i in range(count):
        total = now.year * 12 + (now.month - 1) + i
        yield total // 12, total % 12 + 1


def _date_window(days: int):
    today = store.beijing_date()
    return today.isoformat(), (today + timedelta(days=days)).isoformat()


def _parse_french_date(text: str) -> tuple[str, str | None] | None:
    s = re.sub(r"\s+", " ", text or "").strip()
    m = re.match(r"le\s+(\d{1,2})\s+(\S+)\s+(\d{4})(?:\s+à\s+(\d{1,2})h(\d{2}))?", s, re.I)
    if m:
        mm = FRENCH_MONTHS.get(m.group(2).lower())
        if mm:
            time = f"{int(m.group(4)):02d}:{m.group(5)}" if m.group(4) else None
            return f"{m.group(3)}-{mm}-{int(m.group(1)):02d}", time
    m = re.match(r"du\s+(\d{1,2})\s+(\S+)\s+au\s+(\d{1,2})\s+(\S+)\s+(\d{4})", s, re.I)
    if m:
        mm = FRENCH_MONTHS.get(m.group(2).lower())
        if mm:
            return f"{m.group(5)}-{mm}-{int(m.group(1)):02d}", None
    m = re.match(r"du\s+(\d{1,2})\s+au\s+(\d{1,2})\s+(\S+)\s+(\d{4})", s, re.I)
    if m:
        mm = FRENCH_MONTHS.get(m.group(3).lower())
        if mm:
            return f"{m.group(4)}-{mm}-{int(m.group(1)):02d}", None
    return None


def _parse_sydney_dates(raw: str) -> list[str]:
    text = re.sub(r"\s+", " ", (raw or "").replace("&amp;", "&")).strip()

    def month_num(name):
        return MONTH_ABBR.get(name.capitalize())

    m = re.match(r"^(\d{1,2})\s*&\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})$", text)
    if m:
        mm = month_num(m.group(3))
        if mm:
            return [f"{m.group(4)}-{mm}-{int(m.group(1)):02d}", f"{m.group(4)}-{mm}-{int(m.group(2)):02d}"]
    m = re.match(r"^(\d{1,2})\s*[–—-]\s*(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})$", text)
    if m:
        mm = month_num(m.group(3))
        if mm:
            return [f"{m.group(4)}-{mm}-{d:02d}" for d in range(int(m.group(1)), int(m.group(2)) + 1)]
    m = re.match(r"^(\d{1,2})\s+([A-Za-z]+)\s*[–—-]\s*\d{1,2}\s+[A-Za-z]+\s+(\d{4})$", text)
    if m:
        mm = month_num(m.group(2))
        if mm:
            return [f"{m.group(3)}-{mm}-{int(m.group(1)):02d}"]
    m = re.match(r"^(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})$", text)
    if m:
        mm = month_num(m.group(2))
        if mm:
            return [f"{m.group(3)}-{mm}-{int(m.group(1)):02d}"]
    return []


# ---------- 通用 ics / json ----------

def _feed_ics(feed: dict, house: dict) -> list[dict]:
    text = fetch.fetch_text(feed["url"], timeout=45)
    cal = icalendar.Calendar.from_ical(text)
    items = []
    for comp in cal.walk("VEVENT"):
        summary = str(comp.get("SUMMARY") or "")
        dtstart = comp.get("DTSTART")
        when = None
        if dtstart:
            dt = getattr(dtstart, "dt", None)
            if isinstance(dt, datetime):
                when = dt.date()
            elif isinstance(dt, date):
                when = dt
        if not summary or not when:
            continue
        composer, title = _split_work(summary)
        items.append(
            {
                "composer": composer,
                "title": title,
                "date": when.isoformat(),
                "url": str(comp.get("URL") or "") or house.get("calendar_url", ""),
                "location": str(comp.get("LOCATION") or ""),
            }
        )
    return items


def _split_work(text: str) -> tuple[str, str]:
    text = (text or "").strip()
    for sep in ("：", ":", "–", "—", "-"):
        if sep in text:
            composer, title = text.split(sep, 1)
            if composer.strip() and title.strip():
                return composer.strip(), title.strip()
    return "", text


def _feed_generic_json(feed: dict, house: dict) -> list[dict]:
    url = _expand_dates(feed["url"])
    data = fetch.fetch_json(url, headers={"Accept": "application/json"})
    raw_items = data if isinstance(data, list) else data.get("performances", data.get("items", []))
    fm = feed.get("field_map", {})
    items = []
    for raw in raw_items:
        if not isinstance(raw, dict):
            continue
        if feed.get("skip_when"):
            skip = True
            for k, v in feed["skip_when"].items():
                if raw.get(k) != v:
                    skip = False
            if skip:
                continue
        title = str(raw.get(fm.get("title", "title"), ""))
        when = raw.get(fm.get("date", "date"))
        if not title or not when:
            continue
        m = re.match(r"^(\d{4}-\d{2}-\d{2})T?(\d{2}:\d{2})?", str(when))
        if not m:
            continue
        items.append(
            {
                "composer": str(raw.get(fm.get("composer", "composer"), "")),
                "title": title,
                "date": m.group(1),
                "time": m.group(2),
                "url": str(raw.get(fm.get("url", "url"), "")) or house.get("calendar_url", ""),
                "location": str(raw.get(fm.get("venue", "venue"), "")),
            }
        )
    return items


def _expand_dates(template: str) -> str:
    start, end = _date_window(400)
    return template.replace("{from_date}", start).replace("{to_date}", end)


# ---------- 各家官方接口 ----------

def _feed_roh(feed: dict, house: dict) -> list[dict]:
    items = []
    for year, month in _next_months(3):
        url = feed["url"].replace("{year}", str(year)).replace("{month}", f"{month:02d}")
        data = fetch.fetch_json(url, headers={"Accept": "application/json"})
        items.extend(_parse_roh(data))
    return items


def _parse_roh(data: dict) -> list[dict]:
    included = data.get("included", [])
    events_map = {}
    locations_map = {}
    for res in included:
        attrs = res.get("attributes", {})
        if res.get("type") == "calendarEvent":
            events_map[res["id"]] = attrs
        elif res.get("type") == "locations":
            locations_map[res["id"]] = attrs.get("title", "")

    items = []
    for res in included:
        if res.get("type") != "calendarActivity":
            continue
        attrs = res.get("attributes", {})
        rel = res.get("relationships", {})
        event_id = (rel.get("event", {}).get("data") or {}).get("id")
        cal = events_map.get(event_id)
        if not cal or cal.get("sourceType") == "prismic-only-event-card":
            continue
        title = _strip_html(cal.get("title"))
        if not title:
            continue
        m = re.match(r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})", attrs.get("date", ""))
        if not m:
            continue
        loc_ids = rel.get("locations", {}).get("data") or []
        location = next((locations_map.get(x.get("id")) for x in loc_ids if locations_map.get(x.get("id"))), None)
        subtitle = _strip_html(attrs.get("subtitle"))
        full_title = f"{title} — {subtitle}" if subtitle else title
        items.append(
            {
                "composer": "",
                "title": full_title,
                "date": m.group(1),
                "time": m.group(2),
                "url": _roh_url(cal),
                "location": location or "",
            }
        )
    return items


def _roh_url(cal: dict) -> str:
    base = "https://www.rbo.org.uk"
    if cal.get("link"):
        return urljoin(base + "/", cal["link"])
    slug = cal.get("slug")
    if slug:
        st = cal.get("sourceType")
        if st == "single-production-page":
            return f"{base}/production/{slug}"
        if st == "event-detail":
            return f"{base}/tickets-and-events/{slug}-dates"
        if st == "prismic-only-event-detail":
            return f"{base}/tickets-and-events/{slug}-details"
        if st == "festival":
            return f"{base}/tickets-and-events/festival/{slug}-details"
    return f"{base}/calendar"


def _feed_paris(feed: dict, house: dict) -> list[dict]:
    items = []
    page = 1
    while True:
        url = f"{feed['url']}?page={page}"
        data = fetch.fetch_json(url, headers={"Accept": "application/json"})
        items.extend(_parse_paris(data))
        total = int(data.get("meta", {}).get("pagination", {}).get("total_pages", 1) or 1)
        if page >= total:
            break
        page += 1
        if page > 50:
            break
    return items


def _parse_paris(data: dict) -> list[dict]:
    items = []
    for block in data.get("data", []):
        if block.get("type") != "shows":
            continue
        for show in block.get("shows", []):
            title = show.get("title", "")
            date_text = show.get("start_end_dates", "")
            if not title or not date_text:
                continue
            parsed = _parse_french_date(date_text)
            if not parsed:
                continue
            date_str, time_str = parsed
            sub = show.get("sub_title") or ""
            full_title = f"{title} — {sub}" if sub else title
            items.append(
                {
                    "composer": "",
                    "title": full_title,
                    "date": date_str,
                    "time": time_str,
                    "url": show.get("full_url") or "",
                    "location": show.get("venue") or "",
                }
            )
    return items


def _feed_salzburg(feed: dict, house: dict) -> list[dict]:
    start, end = _date_window(feed.get("window_days", 150))
    body = json.loads(
        json.dumps(feed.get("post_body", {}))
        .replace("{from_date}", start)
        .replace("{to_date}", end)
    )
    data = fetch.fetch_json_post(feed["url"], body)
    items = []
    for e in data:
        if e.get("rehearsal"):
            continue
        m = re.match(r"^(\d{4}-\d{2}-\d{2})T?(\d{2}:\d{2})?", e.get("start", ""))
        if not m:
            continue
        items.append(
            {
                "composer": _strip_html(e.get("header", "")),
                "title": _strip_html(e.get("title", "")),
                "date": m.group(1),
                "time": m.group(2),
                "url": e.get("link") or "",
                "location": _strip_html(e.get("location", "")),
            }
        )
    return items


def _feed_sf(feed: dict, house: dict) -> list[dict]:
    start, end = _date_window(feed.get("window_days", 120))
    url = feed["url"].replace("{from_date}", start).replace("{to_date}", end)
    data = fetch.fetch_json(url, headers={"Accept": "application/json"})
    return [_parse_ace_event(e, base="https://www.sfopera.com") for e in data if _parse_ace_event(e, base="https://www.sfopera.com")]


def _parse_ace_event(e: dict, base: str) -> dict | None:
    if e.get("hideFromCalendar") or e.get("hidePerfFromCal"):
        return None
    name = e.get("name") or ""
    m = re.match(r"^(\d{4}-\d{2}-\d{2})T?(\d{2}:\d{2})?", e.get("eventDate") or "")
    if not name or not m:
        return None
    url = e.get("viewDetailCtaUrl") or ""
    if url.startswith("/"):
        url = base + url
    return {
        "composer": e.get("composerInfo") or "",
        "title": name,
        "date": m.group(1),
        "time": m.group(2),
        "url": url,
        "location": e.get("location") or "",
    }


def _feed_lyric(feed: dict, house: dict) -> list[dict]:
    start, end = _date_window(feed.get("window_days", 400))
    url = feed["url"].replace("{from_date}", start).replace("{to_date}", end)
    data = browser.fetch_json([url], feed.get("warmup_url") or "https://www.lyricopera.org/calendar/")
    return _parse_lyric(data[0])


def _parse_lyric(data: list, today: str | None = None) -> list[dict]:
    today = today or store.beijing_date().isoformat()
    items = []
    for e in data:
        item = _parse_ace_event(e, base="https://www.lyricopera.org")
        if item and item["date"] >= today:
            items.append(item)
    return items


def _feed_met(feed: dict, house: dict) -> list[dict]:
    start, end = _date_window(feed.get("window_days", 90))
    url = feed["url"].replace("{from_date}", start).replace("{to_date}", end)
    data = browser.fetch_json([url], feed.get("warmup_url") or "https://www.metopera.org/calendar/")
    return _parse_met(data[0])


def _parse_met(data: list) -> list[dict]:
    items = []
    for e in data:
        if e.get("hideFromCalendar"):
            continue
        name = e.get("name") or ""
        m = re.match(r"^(\d{4}-\d{2}-\d{2})T?(\d{2}:\d{2})?", e.get("eventDate") or "")
        if not name or not m:
            continue
        conductor = None
        cast = []
        credits = e.get("artistCredits") or ""
        if credits:
            parts = [p.strip() for p in str(credits).split(";")]
            if len(parts) >= 2:
                conductor = parts[0]
                cast = [p.strip() for p in parts[1].split(",") if p.strip()]
            else:
                cast = [p.strip() for p in parts[0].split(",") if p.strip()]
        composer = (e.get("composer") or "").strip()
        url = e.get("viewDetailCtaUrl") or ""
        if url.startswith("/"):
            url = "https://www.metopera.org" + url
        items.append(
            {
                "composer": composer,
                "title": name,
                "date": m.group(1),
                "time": m.group(2),
                "url": url,
                "location": e.get("location") or "",
                "cast": cast,
                "conductor": conductor,
            }
        )
    return items


# ---------- 各家页面解析 ----------

def _feed_vienna(feed: dict, house: dict) -> list[dict]:
    items = []
    for year, month in _next_months(3):
        url = feed["url"].replace("{year}", str(year)).replace("{month}", MONTHS_EN[month - 1])
        try:
            html = fetch.fetch_text(url)
        except Exception as exc:
            if getattr(exc, "code", None) == 404:
                continue
            raise
        items.extend(_parse_vienna(html))
    return items


def _parse_vienna(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    year_match = re.search(r"/calendar/(\d{4})/", html)
    year = year_match.group(1) if year_match else str(store.beijing_date().year)
    items = []
    for group in soup.select("div.event-group"):
        date_map = {}
        for sd in group.select(".date-col .sticky-date"):
            ref = sd.get("data-event", "")
            day = sd.select_one(".production-date-day")
            month = sd.select_one(".production-date-month")
            time_el = sd.select_one(".production-time")
            tm = re.search(r"(\d{2}:\d{2})", time_el.get_text() if time_el else "")
            date_map[ref] = (
                day.get_text().strip() if day else "",
                month.get_text().strip() if month else "",
                tm.group(1) if tm else None,
            )
        for item in group.select(".event-col > .event-list-item"):
            iid = item.get("id", "")
            day, month, time_str = date_map.get(iid, ("", "", None))
            title_el = item.select_one("h2.event-title")
            if not title_el:
                continue
            title = title_el.get_text().strip()
            a = item.select_one('a[href*="/calendar/detail/"]')
            href = a.get("href", "") if a else ""
            m = re.search(r"/(\d{4}-\d{2}-\d{2})/", href)
            if m:
                date_str = m.group(1)
            elif day and month:
                mm = MONTH_ABBR.get(month)
                date_str = f"{year}-{mm}-{day.zfill(2)}" if mm else ""
            else:
                date_str = ""
            if not date_str:
                continue
            room = item.select_one(".event-room")
            lead = item.select_one(".event-lead")
            conductor = None
            cast = []
            sub = item.select_one(".event-subtitle")
            if sub:
                spans = sub.find_all("span")
                if spans:
                    cm = re.search(r"Conductor:\s*(.+)", spans[-1].get_text())
                    if cm:
                        conductor = cm.group(1).replace("\xa0", " ").strip().rstrip(",")
                wm = re.search(r"with\s+(.+)", sub.get_text(" ", strip=True), re.I)
                if wm:
                    cast = [x.strip() for x in wm.group(1).replace("\xa0", " ").split(",") if x.strip()]
            composer = lead.get_text(" ", strip=True).rstrip(",") if lead else ""
            url = urljoin("https://www.wiener-staatsoper.at/", href) if href else ""
            items.append(
                {
                    "composer": composer,
                    "title": title,
                    "date": date_str,
                    "time": time_str,
                    "url": url,
                    "location": room.get_text().strip() if room else "",
                    "cast": cast,
                    "conductor": conductor,
                }
            )
    return items


def _feed_scala(feed: dict, house: dict) -> list[dict]:
    html = fetch.fetch_text(feed["url"])
    return _parse_scala(html)


def _parse_scala(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    today = store.beijing_date().isoformat()
    items = []
    seen = set()
    for art in soup.select("article.mcl-evt"):
        title_el = art.select_one("h2.mcl-evt-title")
        time_el = art.select_one("time.mcl-time")
        if not title_el or not time_el:
            continue
        m = re.match(r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})", time_el.get("datetime", "") or "")
        if not m:
            continue
        date_str, time_str = m.group(1), m.group(2)
        if date_str < today:
            continue
        composer = ""
        authors = art.select("address.mcl-evt-author")
        if authors:
            first = authors[0].get_text().strip()
            if not re.search(r"abb|turno|stagione|abbonamento", first, re.I):
                composer = first
        a = art.find_parent("a")
        href = a.get("href", "") if a else ""
        title = title_el.get_text().strip()
        key = (date_str, time_str, title)
        if key in seen:
            continue
        seen.add(key)
        items.append(
            {
                "composer": composer,
                "title": title,
                "date": date_str,
                "time": time_str,
                "url": urljoin("https://www.teatroallascala.org/", href) if href else "",
            }
        )
    return items


def _feed_zurich(feed: dict, house: dict) -> list[dict]:
    base = feed["url"]
    cutoff = (store.beijing_date() + timedelta(days=90)).isoformat()
    items = []
    seen = set()
    for page in range(1, feed.get("max_pages", 20) + 1):
        url = base if page == 1 else urljoin(base, f"page{page}")
        page_items = _parse_zurich(fetch.fetch_text(url))
        if not page_items:
            break
        added = 0
        for it in page_items:
            if it["date"] > cutoff:
                continue
            key = (it["date"], it["title"])
            if key in seen:
                continue
            seen.add(key)
            items.append(it)
            added += 1
        if added == 0:
            break
    return items


def _parse_zurich(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    header = soup.select_one("h2.new-month")
    default_year = str(store.beijing_date().year)
    if header:
        m = re.search(r"(\d{4})", header.get_text())
        if m:
            default_year = m.group(1)
    current = None
    items = []
    for el in soup.select("div.el-eventlistitem"):
        title_el = el.select_one(".details .inner h2")
        if not title_el:
            continue
        title = title_el.get_text().strip()
        date_str = None
        time_str = None
        ld = el.select_one('script[type="application/ld+json"]')
        if ld:
            try:
                ldj = json.loads(ld.get_text())
                m = re.match(r"^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})", ldj.get("startDate", "") or "")
                if m:
                    date_str, time_str = m.group(1), m.group(2)
            except Exception:
                pass
        if not date_str:
            date_div = el.select_one(".date")
            if date_div:
                day = date_div.select_one(".day")
                month = date_div.select_one(".month")
                if day and month:
                    mm = MONTH_ABBR.get(month.get_text().strip())
                    if mm:
                        current = (day.get_text().strip().zfill(2), mm, default_year)
                if current:
                    date_str = f"{current[2]}-{current[1]}-{current[0]}"
                ps = date_div.find_all("p")
                if ps:
                    tm = re.match(r"^(\d{1,2})\.(\d{2})$", ps[-1].get_text().strip())
                    if tm:
                        time_str = f"{int(tm.group(1)):02d}:{tm.group(2)}"
        if not date_str:
            continue
        loc = el.select_one(".details .inner .location")
        a = el.select_one("a.link-box")
        href = a.get("href", "") if a else ""
        composer = ""
        desc = el.select_one(".details .inner .description")
        if desc:
            d = re.sub(r"CHF[\d\s./]+", "", desc.get_text(" ", strip=True))
            cm = re.search(r"(?:Oper|Ballett|Musiktheater|Requiem)\s+von\s+(.+)", d, re.I)
            if cm:
                composer = cm.group(1).strip()
        items.append(
            {
                "composer": composer,
                "title": title,
                "date": date_str,
                "time": time_str,
                "url": urljoin("https://www.opernhaus.ch/", href) if href else "",
                "location": loc.get_text().strip() if loc else "",
            }
        )
    return items


def _feed_sydney(feed: dict, house: dict) -> list[dict]:
    items = []
    seen = set()
    for page in range(0, feed.get("max_pages", 8)):
        url = feed["url"] if page == 0 else feed["url"] + f"&page={page}"
        page_items = _parse_sydney(fetch.fetch_text(url))
        if not page_items:
            break
        for it in page_items:
            key = (it["date"], it["title"])
            if key in seen:
                continue
            seen.add(key)
            items.append(it)
    return items


def _parse_sydney(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for card in soup.select("div.card.card--whats-on.card--event"):
        title_el = card.select_one(".card__heading span")
        dates_el = card.select_one(".card__dates")
        if not title_el or not dates_el:
            continue
        dates = _parse_sydney_dates(dates_el.get_text(" ", strip=True))
        if not dates:
            continue
        title = title_el.get_text().strip()
        loc = card.select_one(".card__venue")
        a = card.select_one("a.card__link")
        href = a.get("href", "") if a else ""
        for ds in dates:
            items.append(
                {
                    "composer": "",
                    "title": title,
                    "date": ds,
                    "url": urljoin("https://www.sydneyoperahouse.com/", href) if href else "",
                    "location": loc.get_text().strip() if loc else "",
                }
            )
    return items


def _feed_bayreuth(feed: dict, house: dict) -> list[dict]:
    base = "https://www.bayreuther-festspiele.de"
    headers = {"Accept-Language": "en-US,en;q=0.9,de;q=0.8"}
    context = ssl._create_unverified_context() if feed.get("insecure") else None
    html = fetch.fetch_text(feed["url"], headers=headers, context=context)
    soup = BeautifulSoup(html, "html.parser")
    productions = []
    seen_links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        if not re.search(r"/(en/)?spielplan/[a-z0-9-]+/?$", href, re.I):
            continue
        full = urljoin(base + "/", href)
        if full in seen_links:
            continue
        seen_links.add(full)
        title = a.get_text(" ", strip=True) or ""
        productions.append((full, title))

    items = []
    for full, anchor_title in productions[:14]:
        try:
            page = fetch.fetch_text(full, headers=headers, context=context)
        except Exception:
            continue
        title = anchor_title
        if not title:
            tm = re.search(r"<title[^>]*>([^<]+?)\s*[–—-]\s*Bayreuth", page, re.I | re.S)
            if tm:
                title = tm.group(1).strip()
        if not title:
            continue
        dates = set()
        for m in re.finditer(r"(\d{1,2})\.\s*([A-Za-z]+)\s+(\d{4})", page):
            mm = MONTH_FULL.get(m.group(2).lower())
            if mm:
                dates.add(f"{m.group(3)}-{mm}-{int(m.group(1)):02d}")
        for ds in sorted(dates):
            items.append(
                {
                    "composer": "",
                    "title": title,
                    "date": ds,
                    "url": full,
                }
            )
    return items


def _feed_bayerische(feed: dict, house: dict) -> list[dict]:
    last_error = None
    for attempt in range(2):
        try:
            html = browser.fetch_html(
                feed["url"],
                wait_selector=feed.get("wait_selector", ".activity-list__row"),
                timeout=60_000,
                scroll=feed.get("scroll", 5),
            )
            return _parse_bayerische(html)
        except Exception as exc:
            last_error = exc
            time.sleep(5)
    raise last_error


def _parse_bayerische(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    allowed = {"Oper", "Ballett", "Konzert", "Liederabend"}
    items = []
    for row in soup.select(".activity-list__row"):
        date_str = row.get("data-date") or ""
        title_el = row.select_one(".activity-list__text .h3")
        if not date_str or not title_el:
            continue
        genre = row.select_one(".activity-list__col--genre")
        if genre and genre.get_text().strip() not in allowed:
            continue
        title = title_el.get_text().strip()
        info_el = row.select_one(".activity-list__text > span")
        time_str = None
        location = ""
        if info_el:
            info = info_el.get_text().strip()
            tm = re.match(r"^(\d{1,2})\.(\d{2})\s*Uhr", info)
            if tm:
                time_str = f"{int(tm.group(1)):02d}:{tm.group(2)}"
            lm = re.search(r"Uhr\s*\|\s*(.+)", info)
            if lm:
                location = lm.group(1).strip()
        composer = ""
        comp_p = row.select_one(".activity-list--toggle__content p:not(.activity-list-price-info)")
        if comp_p:
            composer = _strip_html(comp_p.get_text())
        a = row.select_one(".activity-list__content")
        href = a.get("href", "") if a else ""
        items.append(
            {
                "composer": composer,
                "title": title,
                "date": date_str,
                "time": time_str,
                "url": urljoin("https://www.staatsoper.de/", href) if href else "",
                "location": location,
            }
        )
    return items


# ---------- 对外入口 ----------

_FEED_HANDLERS = {
    "ics": _feed_ics,
    "json": _feed_generic_json,
    "roh-json": _feed_roh,
    "paris-json": _feed_paris,
    "salzburg-json": _feed_salzburg,
    "sfopera-json": _feed_sf,
    "met-json": _feed_met,
    "lyric-json": _feed_lyric,
    "vienna-html": _feed_vienna,
    "scala-html": _feed_scala,
    "zurich-html": _feed_zurich,
    "sydney-html": _feed_sydney,
    "bayreuth-html": _feed_bayreuth,
    "bayerische-html": _feed_bayerische,
}


def fetch_house(house: dict) -> list[dict]:
    """抓取一家剧院的全部启用订阅源，返回标准化演出条目。"""
    results = []
    today = store.beijing_date().isoformat()
    for feed in house.get("feeds", []):
        if feed.get("enabled") is False:
            continue
        feed_type = feed.get("type", "")
        handler = _FEED_HANDLERS.get(feed_type)
        if not handler:
            continue
        if feed.get("browser") and not browser.available():
            print(
                f"[warn] {house.get('id')} 的 {feed_type} 需要浏览器模式"
                "（本地可设 OP_HUB_ENABLE_BROWSER=1 并安装 playwright 后启用）"
            )
            continue
        try:
            items = handler(feed, house)
        except Exception as exc:
            print(f"[warn] 排期源抓取失败 {house.get('id')} {feed_type}: {exc}")
            continue
        for it in items:
            title = it.get("title", "").strip()
            if not title or not it.get("date") or it["date"] < today:
                continue
            composer = it.get("composer", "").strip()
            display_title = title
            if composer and f"({composer})" not in title:
                display_title = f"{title} ({composer})"
            results.append(
                {
                    "id": store.perf_id(house["id"], composer, title, it["date"], it.get("url", "")),
                    "house": house["id"],
                    "house_name": house.get("name", house["id"]),
                    "composer": composer,
                    "title": display_title,
                    "date": it["date"],
                    "time": it.get("time"),
                    "url": it.get("url", ""),
                    "location": it.get("location", ""),
                    "cast": it.get("cast", []),
                    "conductor": it.get("conductor"),
                    "source_feed": feed_type,
                    "updated_at": store.utc_now_iso(),
                }
            )
    return results
