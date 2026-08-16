"""配置读取。所有配置都放在 config/ 目录下的 JSON 文件里。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"


def _read(path: Path, default):
    if not path.exists():
        return default
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def news_config() -> dict:
    return _read(CONFIG_DIR / "news.json", {"sources": [], "filter_keywords": []})


def houses_config() -> list:
    return _read(CONFIG_DIR / "houses.json", [])


def artists_config() -> list:
    return _read(CONFIG_DIR / "artists.json", [])
