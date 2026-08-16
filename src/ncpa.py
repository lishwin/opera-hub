"""国家大剧院艺术家库：制作档案索引与新闻关联比对。

数据来源：config/ncpa.json（按制作逐一收录主创与主演）。
用法：
    from src import ncpa
    index = ncpa.load_index()
    hits = index.match("和慧将亮相萨尔茨堡音乐节")
    # hits[0] -> {"name": "和慧", "category": "歌唱家", "productions": [...]}
"""
import html
import json
import re
import unicodedata

from . import config

# 制作中角色名 → 艺术家类别
_CATEGORY_BY_ROLE = {
    "指挥": "指挥",
    "导演": "导演",
    "作曲": "作曲家",
    "续创作曲": "作曲家",
    "编剧": "编剧",
    "舞美设计": "舞美设计",
    "服装设计": "服装设计",
    "服装/造型设计": "服装设计",
    "艺术指导": "艺术指导",
    "编舞": "编舞",
}

# 两字中文名后面允许紧接的常见字（避免“张艺”误中“张艺谋”、“张扬”误中“个性张扬”）
_TWO_CHAR_FOLLOW = set(
    "与和同携率指执主导饰演出登亮首复客献独咏卡唱领衔加盟担任将又在再于到赴巡访来华京沪也均曾已为"
    "表称谈说认接受访"
)

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _norm_ascii(text: str) -> str:
    """去掉重音并转小写，便于“Plácido Domingo”与“Placido Domingo”互相匹配。"""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


def _is_ascii(name: str) -> bool:
    return all(ord(ch) < 128 for ch in name)


def _clean(text: str) -> str:
    """去掉 HTML 标签、还原实体并压缩空白。"""
    text = html.unescape(text or "")
    text = _TAG_RE.sub(" ", text)
    return _WS_RE.sub(" ", text).strip()


def _contains_name(text: str, name: str) -> bool:
    if not name or not text:
        return False
    if _is_ascii(name):
        pat = re.compile(
            r"(?<![A-Za-z0-9])" + re.escape(_norm_ascii(name)) + r"(?![A-Za-z0-9])"
        )
        return pat.search(_norm_ascii(text)) is not None

    start = 0
    while True:
        idx = text.find(name, start)
        if idx < 0:
            return False
        before = text[idx - 1] if idx > 0 else ""
        after = text[idx + len(name)] if idx + len(name) < len(text) else ""
        # 三字以上中文名基本无歧义，直接命中
        if len(name) >= 3:
            return True
        # 两字中文名：仅当 结尾为边界/标点/常见后缀字 时命中，
        # 避免“张艺”误中“张艺谋”、“万方”误中“万方数据”
        if not _CJK_RE.match(after) or after in _TWO_CHAR_FOLLOW:
            return True
        start = idx + 1


class NcpaIndex:
    """把 config/ncpa.json 组织成 艺术家 → 制作 的索引，并提供新闻比对。"""

    def __init__(self, data: dict):
        self.data = data
        self.productions = {p["id"]: p for p in data.get("productions", [])}
        # 艺术家规范中文名 -> 艺术家档案
        self.artists: dict[str, dict] = {}
        self._build_artists()
        self._link_productions()

    def _add_artist(self, name: str, name_en: list[str], category: str) -> None:
        name = (name or "").strip()
        if not name:
            return
        entry = self.artists.setdefault(
            name,
            {"name": name, "name_en": [], "category": "", "prod_ids": []},
        )
        for en in name_en or []:
            if en and en not in entry["name_en"]:
                entry["name_en"].append(en)
        if category and not entry["category"]:
            entry["category"] = category

    def _build_artists(self) -> None:
        # 1) aliases：已整理好的中英文名对照
        for cn, info in self.data.get("aliases", {}).items():
            self._add_artist(cn, info.get("name_en", []), info.get("category", ""))
        # 2) 从每部制作的主创与卡司中补全未收录的艺术家
        for p in self.productions.values():
            for role, names in p.get("roles", {}).items():
                category = _CATEGORY_BY_ROLE.get(role, role)
                for n in names:
                    self._add_artist(n, [], category)
            for c in p.get("cast", []):
                name = c.get("name") if isinstance(c, dict) else str(c)
                if name:
                    self._add_artist(name, [], "歌唱家")

    def _link_productions(self) -> None:
        """把每部制作关联到其中出现过的艺术家（含 notes 中提到的复排指挥等）。"""
        for artist in self.artists.values():
            variants = [artist["name"]] + [en for en in artist.get("name_en", []) if en]
            if not variants:
                continue
            for prod in self.productions.values():
                text = _clean(self._production_text(prod))
                if any(_contains_name(text, v) for v in variants):
                    artist["prod_ids"].append(prod["id"])

    @staticmethod
    def _production_text(p: dict) -> str:
        parts = [p.get("title"), p.get("composer"), p.get("type"), p.get("notes")]
        for role, names in p.get("roles", {}).items():
            parts.append(role)
            parts.extend(names)
        for c in p.get("cast", []):
            if isinstance(c, dict):
                parts.extend([c.get("name", ""), c.get("role", "")])
            else:
                parts.append(str(c))
        return "\n".join(str(x) for x in parts if x)

    @staticmethod
    def _find_role(p: dict, variants: list[str]) -> str | None:
        """在制作中查找艺术家承担的角色（如“指挥”“饰 阿依达”）。"""
        for role, names in p.get("roles", {}).items():
            if any(n in variants for n in names):
                return role
        for c in p.get("cast", []):
            if not isinstance(c, dict):
                continue
            if c.get("name") in variants:
                return f"饰 {c['role']}" if c.get("role") else "歌唱家"
        return None

    def match(self, text: str) -> list[dict]:
        """在新闻标题+摘要中查找与大剧院合作过的艺术家。

        返回命中列表，每项含艺术家信息及其在大剧院的合作制作。
        """
        text = _clean(text)
        hits = []
        for artist in self.artists.values():
            variants = [artist["name"]] + [en for en in artist.get("name_en", []) if en]
            if not any(_contains_name(text, v) for v in variants):
                continue
            productions = []
            for pid in artist["prod_ids"]:
                p = self.productions[pid]
                productions.append(
                    {
                        "year": p.get("year"),
                        "title": p.get("title"),
                        "composer": p.get("composer", ""),
                        "role": self._find_role(p, variants),
                    }
                )
            productions.sort(key=lambda x: x["year"] or 0)
            hits.append(
                {
                    "name": artist["name"],
                    "category": artist.get("category", ""),
                    "name_en": artist.get("name_en", []),
                    "productions": productions,
                }
            )
        # 合作制作多的艺术家排前面，便于快速浏览
        hits.sort(key=lambda h: (-len(h["productions"]), h["name"]))
        return hits


_CACHE: NcpaIndex | None = None


def load_index() -> NcpaIndex:
    global _CACHE
    if _CACHE is None:
        path = config.CONFIG_DIR / "ncpa.json"
        _CACHE = NcpaIndex(json.loads(path.read_text(encoding="utf-8")))
    return _CACHE
