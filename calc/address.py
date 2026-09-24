"""地址 → 行政區 → 管轄地方法院（決定論式，零 LLM）。

為什麼不讓模型自己認：
  ① 「大安區」臺北市有、臺中市也有——模型幾乎一定答臺北。
  ② 新北市一個市切給**四家**地方法院（臺北／士林／新北／基隆），
     地址只寫到「新北市」根本定不出法院。
  ③ 「東區」「北區」「南區」臺中、臺南都有。
故本模組只做字串比對與查表，**撞名時回候選、不猜**；
判不出來就說判不出來，由使用者或模型補問。
"""
from __future__ import annotations
import os, re, unicodedata
import yaml
from .dates import CalcError

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA = os.path.join(_HERE, "data", "court_jurisdiction.yaml")
_CACHE: dict = {}

CITIES = ["臺北市", "新北市", "桃園市", "臺中市", "臺南市", "高雄市", "基隆市", "新竹市",
          "新竹縣", "苗栗縣", "彰化縣", "南投縣", "雲林縣", "嘉義市", "嘉義縣", "屏東縣",
          "宜蘭縣", "花蓮縣", "臺東縣", "澎湖縣", "金門縣", "連江縣"]
SPECIAL_ISLANDS = {"東沙島": ("高雄市", "東沙島"), "太平島": ("高雄市", "太平島"),
                   "烏坵鄉": ("金門縣", "烏坵鄉")}
OVERSEAS = {"亞洲": 37, "歐洲": 44, "北美洲": 44, "南美洲": 44, "大洋洲": 44,
            "非洲": 72, "南極洲": 72}


def normalize(s: str) -> str:
    """台→臺、全形數字→半形、去郵遞區號與贅詞。"""
    s = unicodedata.normalize("NFKC", str(s or "")).strip()
    s = s.replace("台", "臺").replace("黑", "黑")
    s = re.sub(r"^\s*\d{3,6}\s*", "", s)          # 開頭郵遞區號
    s = s.replace("臺灣省", "").replace("福建省", "").replace("中華民國", "")
    return s


def _load():
    if not _CACHE or _CACHE.get("_mtime") != os.path.getmtime(_DATA):
        with open(_DATA, encoding="utf-8") as f:
            d = yaml.safe_load(f)
        idx_city, idx_dist = {}, {}
        for c in d["courts"]:
            for a in c["areas"]:
                rec = {"court": c["court"], "days": a["days"],
                       "high_court": a.get("high_court", ""), "raw": a["raw"]}
                if a["kind"] == "whole":
                    idx_city.setdefault(a["city"], []).append(rec)
                elif a["kind"] == "special":
                    for nm in a["districts"]:
                        idx_dist.setdefault((None, nm), []).append(rec)
                else:
                    for dt in a["districts"]:
                        idx_dist.setdefault((a["city"], dt), []).append(rec)
                    if not a["districts"] and "東沙島" in a["raw"]:
                        for nm in ("東沙島", "太平島"):
                            idx_dist.setdefault((a["city"], nm), []).append(rec)
        _CACHE.clear()
        _CACHE.update({"_mtime": os.path.getmtime(_DATA), "data": d,
                       "by_city": idx_city, "by_dist": idx_dist})
    return _CACHE


def resolve(address: str, city: str | None = None, district: str | None = None, **_):
    """回傳 {ok, city, district, courts, ambiguous, candidates, note}。"""
    db = _load()
    raw = address or ""
    s = normalize(raw)
    if city:
        city = normalize(city)
    if district:
        district = normalize(district)

    # 境外
    for region in OVERSEAS:
        if region in s:
            return {"ok": True, "scope": "overseas", "region": region,
                    "transit_days": OVERSEAS[region], "input": raw,
                    "basis": "在途期間標準§3 三、居住於國外者"}
    if re.search(r"大陸地區|中國大陸|香港|澳門|港澳", s):
        return {"ok": True, "scope": "mainland_hk_mo", "transit_days": 37, "input": raw,
                "basis": "在途期間標準§3 二、居住於大陸或港澳地區者"}

    # 特例離島
    for nm, (ct, dt) in SPECIAL_ISLANDS.items():
        if nm in s or district == nm:
            city, district = ct, nm

    if not city:
        hit = [c for c in CITIES if c in s]
        city = max(hit, key=len) if hit else None
    if not district:
        cands = [d for (c, d) in db["by_dist"] if d in s and (c is None or c == city or city is None)]
        district = max(cands, key=len) if cands else None

    # 整縣市轄區（宜蘭縣、花蓮縣…）：只要縣市就夠
    # 特例列（烏坵鄉、東沙島、太平島）日數與整縣市不同，須優先於整縣市比對
    _specific = (city, district) in db["by_dist"] or (None, district) in db["by_dist"]
    if city and city in db["by_city"] and not _specific:
        recs = db["by_city"][city]
        return {"ok": True, "scope": "domestic", "city": city, "district": district,
                "matched_by": "whole_city", "courts": recs, "ambiguous": False,
                "input": raw, "note": f"{city}全境由 {recs[0]['court']} 管轄，地址無須精確到鄉鎮市區"}

    if city and district:
        recs = db["by_dist"].get((city, district)) or db["by_dist"].get((None, district))
        if recs:
            return {"ok": True, "scope": "domestic", "city": city, "district": district,
                    "matched_by": "city+district", "courts": recs,
                    "ambiguous": len({r["court"] for r in recs}) > 1, "input": raw}

    if district and not city:
        hits = {(c, d): v for (c, d), v in db["by_dist"].items() if d == district}
        if len(hits) == 1:
            (c, d), recs = next(iter(hits.items()))
            return {"ok": True, "scope": "domestic", "city": c, "district": d,
                    "matched_by": "district_only", "courts": recs, "ambiguous": False,
                    "input": raw, "note": "地址未載縣市，但此區名全國唯一"}
        if len(hits) > 1:
            return {"ok": False, "scope": "domestic", "district": district, "input": raw,
                    "ambiguous": True, "error": f"「{district}」跨縣市同名，無法定管轄法院",
                    "candidates": [{"city": c, "court": v[0]["court"]} for (c, d), v in hits.items()],
                    "advice": "請補縣市；本工具不猜"}

    if city and not district:
        courts = sorted({r["court"] for (c, d), v in db["by_dist"].items() if c == city for r in v})
        if len(courts) > 1:
            return {"ok": False, "scope": "domestic", "city": city, "input": raw,
                    "ambiguous": True,
                    "error": f"{city}分屬 {len(courts)} 家地方法院，只到縣市無法定管轄法院",
                    "candidates": courts,
                    "advice": "請補行政區（區／鄉／鎮／市）；本工具不猜"}
        if courts:
            recs = [r for (c, d), v in db["by_dist"].items() if c == city for r in v]
            return {"ok": True, "scope": "domestic", "city": city, "matched_by": "city_single_court",
                    "courts": recs[:1], "ambiguous": False, "input": raw}

    return {"ok": False, "input": raw, "error": "無法由地址判定行政區",
            "advice": "請提供縣市與行政區，或改用 city／district 參數直接指定"}
