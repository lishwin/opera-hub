"""JSON 数据的读写与去重状态管理。"""
import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

# 以北京时间作为日报与时间过滤的基准
BEIJING_TZ = timezone(timedelta(hours=8), name="Asia/Shanghai")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def beijing_now():
    return datetime.now(BEIJING_TZ)


def beijing_date():
    return beijing_now().date()


def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return default


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def perf_id(house_id: str, composer: str, title: str, first_date: str, url: str) -> str:
    """根据演出要素生成稳定 ID，用于去重与合并。"""
    raw = f"{house_id}|{composer}|{title}|{first_date}|{url}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
