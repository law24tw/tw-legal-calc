"""上訴／抗告／再審期間試算（民事、刑事；決定論、零 LLM）。

公式對照司法院辦案小工具「上訴抗告再審期間試算」的試算結果欄：
  總期間 = 不變期間(A) + 在途期間(B) + 寄存／公示送達生效期間(C)
  B：當事人居住於原審法院管轄區域內 → 在途期間標準§2 附表該區日數；
     非居住於管轄區域內 → (i) 原審法院區域之在途期間日數 + (ii) 居住地地方法院管轄區域內之在途期間日數（§3 一(一)），
     北院／士林／新北、高雄／橋頭、金門／連江之間另依§3 一(二)～(四)；大陸港澳 37 日、國外依洲別（§3 二、三）。
  末日＝收受日＋總期間（始日不算入，民法§120Ⅱ）；末日為星期日、紀念日或其他休息日者以次日代之
  （民訴§161／刑訴§65 → 民法§122）。因天然災害停止上班之日亦為休息日，以受理書狀處所為準
  （最高法院86年度台聲字第121號、86年度台簡聲字第11號民事裁定；103年度台抗字第874號刑事裁定＝在監被告看監所所在地）。

不做的事（誠實邊界）：行政訴訟、智慧財產及商業法院、懲戒法院；再審期間起算點（判決確定或知悉再審理由，民訴§500Ⅱ）
由使用者判定後輸入；在監被告之在途期間基準地；半日停班落在末日者──皆回旗標、不代判。
"""
from __future__ import annotations
import os
from datetime import date, timedelta
import yaml
from .dates import CalcError, to_date, roc
from . import address as _addr

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CAL = os.path.join(_HERE, "data", "office_calendar.yaml")
_CAL_CACHE: dict = {}

PERIODS = {
    ("civil", "appeal"): (20, "民事訴訟法§440"),
    ("civil", "interlocutory"): (10, "民事訴訟法§487"),
    ("civil", "retrial"): (30, "民事訴訟法§500Ⅰ（起算點依§500Ⅱ，由使用者判定後輸入）"),
    ("criminal", "appeal"): (20, "刑事訴訟法§349"),
    ("criminal", "interlocutory"): (10, "刑事訴訟法§406"),
}
SERVICE = {  # 送達生效期間(C)
    ("civil", "normal"): (0, None),
    ("civil", "deposit"): (10, "民事訴訟法§138Ⅱ（自寄存之日起經十日生效）"),
    ("civil", "public"): (20, "民事訴訟法§152"),
    ("civil", "public_abroad"): (60, "民事訴訟法§152（應於外國送達者）"),
    ("criminal", "normal"): (0, None),
    ("criminal", "deposit"): (10, "刑事訴訟法§62 準用民事訴訟法§138Ⅱ"),
    ("criminal", "public"): (30, "刑事訴訟法§60Ⅱ"),
}
# §3 一(一) 括號內的定值
I_LOCAL = {"高雄地方法院": 4, "高雄少年及家事法院": 4, "金門地方法院": 19}
I_HIGH = {"臺灣高等法院高雄分院": 8, "福建高等法院金門分院": 20}
NORTH = {"臺北地方法院", "士林地方法院", "新北地方法院"}
KAO = {"高雄地方法院", "橋頭地方法院"}
KAO_TO_QIAOTOU_2 = {"鹽埕區", "鼓山區", "三民區", "新興區", "前金區", "苓雅區", "前鎮區", "旗津區", "小港區"}
KAO_TO_KAOHSIUNG_2 = {"左營區", "楠梓區", "橋頭區", "岡山區", "燕巢區", "大社區", "仁武區", "彌陀區", "梓官區"}
KM = {"金門地方法院", "連江地方法院"}


def _norm_court(name: str) -> str:
    s = _addr.normalize(name or "").replace(" ", "")
    s = s.replace("地院", "地方法院").replace("高分院", "高等法院分院")
    for p in ("臺灣", "福建"):
        if s.startswith(p) and "地方法院" in s:
            s = s[len(p):]
        if s.startswith(p) and "少年及家事法院" in s:
            s = s[len(p):]
    return s


def _courts():
    d = _addr._load()["data"]["courts"]
    local = {c["court"]: c for c in d}
    high = {}
    for c in d:
        for a in c["areas"]:
            if a.get("high_court"):
                high.setdefault(a["high_court"], []).append(a)
    return local, high


def _calendar():
    if not os.path.exists(_CAL):
        return None
    m = os.path.getmtime(_CAL)
    if _CAL_CACHE.get("_mtime") != m:
        with open(_CAL, encoding="utf-8") as f:
            y = yaml.safe_load(f) or {}
        days = {}
        for r in y.get("days") or []:
            days[str(r["date"])] = bool(r.get("is_holiday"))
        _CAL_CACHE.clear()
        _CAL_CACHE.update({"_mtime": m, "days": days, "meta": y.get("meta") or {}})
    return _CAL_CACHE


def _residence(address, city, district):
    r = _addr.resolve(address=address or "", city=city, district=district)
    if not r.get("ok"):
        raise CalcError("當事人住居所無法定管轄法院：" + (r.get("error") or "")
                        + ("；候選：" + "、".join(str(c) for c in r.get("candidates", [])) if r.get("candidates") else ""))
    if r.get("scope") in ("overseas", "mainland_hk_mo"):
        return r, None
    recs = [x for x in r["courts"] if "少年及家事" not in x["court"]] or r["courts"]
    if len({x["court"] for x in recs}) > 1:
        raise CalcError("住居所對應多家地方法院，請補行政區：" + "、".join(sorted({x["court"] for x in recs})))
    return r, recs[0]


def _transit(filing: str, res: dict, rec: dict | None, local: dict, high: dict):
    """回 (within, i, ii, B, basis)。"""
    if res.get("scope") in ("overseas", "mainland_hk_mo"):
        return False, None, None, res["transit_days"], res.get("basis")
    dist = res.get("district")
    R = rec["court"]
    if filing == "最高法院":
        return True, None, None, rec["days"]["supreme"], "在途期間標準§2（最高法院欄）"
    if filing in high:                                   # 原審為高等法院（分院）
        if rec.get("high_court") == filing:
            return True, None, None, rec["days"]["high"], "在途期間標準§2（高等法院欄）"
        i = I_HIGH.get(filing, max(a["days"]["high"] for a in high[filing]))
        ii = _ii(R, dist, local)
        return False, i, ii, i + ii, "在途期間標準§3 一(一)"
    if filing not in local:
        raise CalcError(f"原審法院「{filing}」不在本工具範圍（支援各地方法院、高等法院及分院、最高法院）")
    if R == filing:
        return True, None, None, rec["days"]["local"], "在途期間標準§2（地方法院欄）"
    if R in NORTH and filing in NORTH:
        zero = res.get("city") == "臺北市" and {R, filing} == {"臺北地方法院", "士林地方法院"}
        return False, None, None, 0 if zero else 2, "在途期間標準§3 一(二)"
    if R in KAO and filing in KAO:
        if dist in ("東沙島", "太平島") and filing == "橋頭地方法院":
            b = 30
        elif (dist in KAO_TO_QIAOTOU_2 and filing == "橋頭地方法院") or (dist in KAO_TO_KAOHSIUNG_2 and filing == "高雄地方法院"):
            b = 2
        else:
            b = 4
        return False, None, None, b, "在途期間標準§3 一(三)"
    if R in KM and filing in KM:
        return False, None, None, 20, "在途期間標準§3 一(四)"
    i = I_LOCAL.get(filing, max(a["days"]["local"] for a in local[filing]["areas"]))
    ii = _ii(R, dist, local)
    return False, i, ii, i + ii, "在途期間標準§3 一(一)"


def _ii(R, dist, local):
    if R in ("高雄地方法院", "高雄少年及家事法院"):
        return 30 if dist in ("東沙島", "太平島") else 4
    if R == "金門地方法院":
        return 30 if dist == "烏坵鄉" else 19
    return max(a["days"]["local"] for a in local[R]["areas"])


def deadline(category="civil", action="appeal", court="", received=None, service="normal",
             address="", city=None, district=None, agent_in_court_location=False,
             check_holidays=True, closures=None, in_custody=False, **_):
    cat, act = str(category).lower(), str(action).lower()
    alias = {"民事": "civil", "刑事": "criminal", "上訴": "appeal", "抗告": "interlocutory", "再審": "retrial",
             "一般": "normal", "寄存": "deposit", "公示": "public", "公示送達": "public"}
    cat, act, svc = alias.get(cat, cat), alias.get(act, act), alias.get(str(service), str(service))
    if cat not in ("civil", "criminal"):
        raise CalcError("本版只支援民事、刑事；行政訴訟期間與在途期間另有規定，尚未收錄")
    if (cat, act) not in PERIODS:
        raise CalcError(f"不支援的程序：{category}／{action}（民事：上訴、抗告、再審；刑事：上訴、抗告）")
    if (cat, svc) not in SERVICE:
        raise CalcError(f"不支援的送達方式：{service}")
    if received is None:
        raise CalcError("缺裁判收受日（寄存送達請填寄存日；公示送達請填公告或最後登載日）")
    d0 = to_date(received)
    A, a_basis = PERIODS[(cat, act)]
    C, c_basis = SERVICE[(cat, svc)]
    filing = _norm_court(court)
    local, high = _courts()
    flags = []

    res, rec = _residence(address, city, district)
    within, i, ii, B, b_basis = _transit(filing, res, rec, local, high)
    if agent_in_court_location and cat == "civil":
        within, i, ii, B, b_basis = within, None, None, 0, "民事訴訟法§162Ⅰ但書（訴訟代理人住居法院所在地，不扣除在途期間）"
    if agent_in_court_location and cat == "criminal":
        flags.append("刑事訴訟法§66 無『訴訟代理人住居法院所在地』之但書，本工具仍依被告住居所計在途期間")
    if in_custody and cat == "criminal":
        flags.append("在監所之被告：向監所長官提出書狀視為期間內（刑訴§351Ⅰ）；在途期間以何地為基準請承辦人判定，本工具依輸入之住居所計算")
    if act == "retrial":
        flags.append("再審期間起算點（判決確定時／送達時／知悉再審理由時，民訴§500Ⅱ）由使用者判定；本工具以輸入日期為起算基準，且自判決確定後逾五年者不得提起（同條但書）")

    total = A + B + C
    raw_last = d0 + timedelta(days=total)
    out = {
        "court": filing, "category": cat, "action": act, "service": svc, "received": roc(d0),
        "within_jurisdiction": within, "transit_i": i, "transit_ii": ii,
        "period_A": A, "transit_B": B, "service_C": C, "total_days": total,
        "last_day_raw": roc(raw_last), "last_day_raw_weekday": "一二三四五六日"[raw_last.weekday()],
        "basis": [a_basis, b_basis] + ([c_basis] if c_basis else []) + ["民法§120Ⅱ（始日不算入）"],
    }
    if res.get("scope") in ("overseas", "mainland_hk_mo"):
        out["residence"] = res.get("region") or "大陸或港澳地區"
    else:
        out["residence"] = f"{res.get('city', '')}{res.get('district') or ''}（{rec['court']}）"

    # 末日順延
    closed = {}
    for c in closures or []:
        if isinstance(c, dict):
            closed[to_date(c["date"])] = "half" if c.get("half") else "full"
        else:
            closed[to_date(c)] = "full"
    last, shifted = raw_last, []
    if check_holidays:
        cal = _calendar()
        if cal is None or str(raw_last) not in cal["days"]:
            flags.append(f"辦公日曆缺 {raw_last.year} 年資料：末日未依國定假日／補班日順延，請人工確認（週六補班日非休息日，法務部99.02.03函）")
            while closed.get(last) == "full":
                shifted.append(f"{roc(last)} 天然災害停止上班"); last += timedelta(days=1)
        else:
            while True:
                hol = cal["days"].get(str(last))
                if hol is None:
                    flags.append(f"辦公日曆缺 {roc(last)}，順延中斷，請人工確認"); break
                if hol:
                    shifted.append(f"{roc(last)} 休息日"); last += timedelta(days=1); continue
                if closed.get(last) == "full":
                    shifted.append(f"{roc(last)} 天然災害停止上班"); last += timedelta(days=1); continue
                break
            out["calendar_source"] = cal["meta"].get("source") or "行政院人事行政總處 政府行政機關辦公日曆表"
        if closed.get(last) == "half":
            flags.append(f"{roc(last)} 為半日停止上班：是否順延，實務未見明確見解，請人工判定")
        if shifted:
            out["basis"].append("民法§122；天然災害停止上班依最高法院86台聲121、86台簡聲11、103台抗874")
    out["last_day"] = roc(last)
    out["last_day_weekday"] = "一二三四五六日"[last.weekday()]
    out["shifted"] = shifted
    out["flags"] = flags
    out["caution"] = "不變期間逾期即失權。本結果為試算，應以送達證書、法院公告之停止上班情形與辦公日曆覆核。"
    return out
