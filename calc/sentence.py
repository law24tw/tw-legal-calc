"""法定刑度加重減輕試算（刑法§33、§64~§73）→ 處斷刑範圍＋宣告刑逾越檢查。

條文於 2026-09-24 逐條經 LFinder :8022 核實 effective_status=現行。

適用之加減例：
  §64Ⅰ 死刑不得加重；§64Ⅱ 死刑減輕者為無期徒刑
  §65Ⅰ 無期徒刑不得加重；§65Ⅱ 無期徒刑減輕者為二十年以下十五年以上有期徒刑
  §66   有期徒刑、拘役、罰金減輕者，減輕其刑至二分之一；同時有免除其刑之規定者，得減至三分之二
  §67   有期徒刑或罰金加減者，其**最高度及最低度同加減之**
  §68   拘役加減者，**僅加減其最高度**
  §70   有二種以上刑之加重或減輕者，**遞加或遞減之**
  §71Ⅰ 刑有加重及減輕者，**先加後減**
  §71Ⅱ 有二種以上之減輕者，**先依較少之數減輕之**
  §72   因刑之加重減輕而有不滿一日之時間或不滿一元之額數者，不算
  §33③ 有期徒刑二月以上十五年以下；遇有加減時，得減至二月未滿，或**加至二十年**
  §33④ 拘役一日以上六十日未滿；遇有加重時，**得加至一百二十日**
  §33⑤ 罰金新臺幣一千元以上，以百元計算之
"""
from __future__ import annotations
from fractions import Fraction as F
from .dates import CalcError

PRISON_CAP_MONTHS = 240          # §33③但書：加至二十年
DETENTION_CAP_DAYS = 120         # §33④但書：加至一百二十日
FRACTIONS = {"1/2": F(1, 2), "1/3": F(1, 3), "2/3": F(2, 3),
             "二分之一": F(1, 2), "三分之一": F(1, 3), "三分之二": F(2, 3)}


def _frac(v):
    if isinstance(v, F):
        return v
    s = str(v).strip()
    if s in FRACTIONS:
        return FRACTIONS[s]
    if "/" in s:
        a, b = s.split("/")
        return F(int(a), int(b))
    raise CalcError(f"加減比例只支援 1/2、1/3、2/3（收到 {v!r}）")


def _fmt_months(m: F) -> str:
    if m is None:
        return "-"
    if m <= 0:
        return "0"
    y, rem = divmod(m, 12)
    mo = int(rem)
    day = int(round(float((rem - mo) * 30)))
    parts = []
    if y:
        parts.append(f"{int(y)}年")
    if mo:
        parts.append(f"{mo}月")
    if day:
        parts.append(f"{day}日")
    return "".join(parts) or "未滿1日"


def _fmt(kind, lo, hi):
    if kind == "death":
        return "死刑"
    if kind == "life":
        return "無期徒刑"
    if kind == "prison":
        return f"{_fmt_months(lo)}以上{_fmt_months(hi)}以下有期徒刑"
    if kind == "detention":
        return f"{int(lo)}日以上{int(hi)}日以下拘役"
    if kind == "fine":
        return f"罰金新臺幣{int(lo):,}元以上{int(hi):,}元以下"
    return "?"


def sentence_range(kind="prison", min_months=None, max_months=None,
                   min_days=None, max_days=None, min_amount=None, max_amount=None,
                   adjustments=None, declared_months=None, declared_days=None,
                   declared_amount=None, **_):
    """回傳處斷刑範圍與逐步計算；給 declared_* 時一併判斷有無逾越。"""
    adj = list(adjustments or [])
    steps = []

    # ── 初始法定刑 ───────────────────────────────────────
    if kind == "prison":
        lo = F(2) if min_months is None else F(str(min_months))
        hi = F(15 * 12) if max_months is None else F(str(max_months))
        if hi <= 0 or lo < 0 or lo > hi:
            raise CalcError("有期徒刑上下限不合（單位＝月）")
    elif kind == "detention":
        lo = F(1) if min_days is None else F(str(min_days))
        hi = F(59) if max_days is None else F(str(max_days))
    elif kind == "fine":
        lo = F(1000) if min_amount is None else F(str(min_amount))
        hi = F(str(max_amount)) if max_amount is not None else None
        if hi is None:
            raise CalcError("罰金須給 max_amount")
    elif kind in ("death", "life"):
        lo = hi = None
    else:
        raise CalcError("kind 需為 death／life／prison／detention／fine")

    steps.append({"stage": "法定刑", "kind": kind, "range": _fmt(kind, lo, hi), "basis": "刑法§33"})

    # ── §71Ⅰ 先加後減；§71Ⅱ 二種以上減輕先依較少之數 ────
    for a in adj:
        if a.get("type") not in ("aggravate", "mitigate", "加重", "減輕"):
            raise CalcError("adjustments[].type 需為 aggravate／mitigate")
    ag = [a for a in adj if a.get("type") in ("aggravate", "加重")]
    mi = [a for a in adj if a.get("type") in ("mitigate", "減輕")]
    mi.sort(key=lambda a: _frac(a.get("fraction", "1/2")))      # §71Ⅱ 較少之數先
    order = ag + mi
    if ag and mi:
        steps.append({"stage": "順序", "note": "刑有加重及減輕者先加後減（§71Ⅰ）；"
                                               "二種以上減輕先依較少之數減輕之（§71Ⅱ）"})

    for a in order:
        f = _frac(a.get("fraction", "1/2"))
        is_ag = a.get("type") in ("aggravate", "加重")
        label = a.get("label", "")
        basis = a.get("basis", "")
        if kind == "death":
            if is_ag:
                steps.append({"stage": "加重", "label": label, "basis": basis,
                              "note": "死刑不得加重（§64Ⅰ）——本次加重不生效果",
                              "range": _fmt(kind, lo, hi)})
                continue
            kind, lo, hi = "life", None, None
            steps.append({"stage": "減輕", "label": label, "basis": basis or "刑法§64Ⅱ",
                          "note": "死刑減輕者為無期徒刑（§64Ⅱ）", "range": "無期徒刑"})
            continue
        if kind == "life":
            if is_ag:
                steps.append({"stage": "加重", "label": label, "basis": basis,
                              "note": "無期徒刑不得加重（§65Ⅰ）——本次加重不生效果",
                              "range": "無期徒刑"})
                continue
            kind, lo, hi = "prison", F(15 * 12), F(20 * 12)
            steps.append({"stage": "減輕", "label": label, "basis": basis or "刑法§65Ⅱ",
                          "note": "無期徒刑減輕者為二十年以下十五年以上有期徒刑（§65Ⅱ）",
                          "range": _fmt(kind, lo, hi)})
            continue

        before = _fmt(kind, lo, hi)
        if kind == "detention":
            # §68 拘役加減者，僅加減其最高度
            hi = hi * (1 + f) if is_ag else hi * (1 - f)
            rule = "§68 拘役僅加減其最高度"
            if is_ag:
                hi = min(hi, F(DETENTION_CAP_DAYS))
                rule += "；§33④但書 加至一百二十日為限"
        else:
            # §67 有期徒刑或罰金，最高度及最低度同加減之
            mult = (1 + f) if is_ag else (1 - f)
            lo, hi = lo * mult, hi * mult
            rule = "§67 最高度及最低度同加減之"
            if kind == "prison" and is_ag:
                if hi > PRISON_CAP_MONTHS:
                    hi = F(PRISON_CAP_MONTHS)
                    rule += "；§33③但書 加至二十年為限"
                lo = min(lo, F(PRISON_CAP_MONTHS))
            if kind == "fine":
                lo = F(max(100, int(lo) // 100 * 100))          # §33⑤ 以百元計算
                hi = F(int(hi) // 100 * 100)
                rule += "；§33⑤ 以百元計算、§72 不滿一元不算"
        steps.append({"stage": "加重" if is_ag else "減輕",
                      "label": label, "basis": basis, "fraction": str(f),
                      "rule": rule, "before": before, "after": _fmt(kind, lo, hi)})

    if len(order) > 1:
        steps.append({"stage": "遞加遞減", "note": "有二種以上刑之加重或減輕者，遞加或遞減之（§70）——"
                                                   "上表各次係就前次結果續行加減，非就法定刑各算一次"})

    out = {"final_kind": kind, "range_text": _fmt(kind, lo, hi), "steps": steps,
           "basis": ["刑法§33", "§64", "§65", "§66", "§67", "§68", "§70", "§71", "§72"]}
    if kind == "prison":
        out["range_months"] = {"min": float(lo), "max": float(hi),
                               "min_text": _fmt_months(lo), "max_text": _fmt_months(hi)}
    elif kind == "detention":
        out["range_days"] = {"min": float(lo), "max": float(hi)}
    elif kind == "fine":
        out["range_amount"] = {"min": int(lo), "max": int(hi)}

    # ── 宣告刑逾越檢查 ───────────────────────────────────
    dec = None
    if declared_months is not None:
        dec, dk, dtxt = F(str(declared_months)), "prison", _fmt_months(F(str(declared_months)))
    elif declared_days is not None:
        dec, dk, dtxt = F(str(declared_days)), "detention", f"{declared_days}日"
    elif declared_amount is not None:
        dec, dk, dtxt = F(str(declared_amount)), "fine", f"新臺幣{int(declared_amount):,}元"
    if dec is not None:
        if dk != kind:
            out["declared_check"] = {"ok": False, "declared": dtxt,
                                     "error": f"宣告刑種（{dk}）與處斷刑種（{kind}）不符",
                                     "verdict": "刑種錯誤"}
        else:
            over_hi, under_lo = dec > hi, dec < lo
            out["declared_check"] = {
                "declared": dtxt, "range": _fmt(kind, lo, hi),
                "ok": not (over_hi or under_lo),
                "exceeds_max": bool(over_hi), "below_min": bool(under_lo),
                "verdict": ("逾越處斷刑上限" if over_hi else
                            "低於處斷刑下限" if under_lo else "在處斷刑範圍內"),
                "note": ("宣告刑逾越處斷刑＝違法，上級審應撤銷" if over_hi else
                         "宣告刑低於處斷刑下限＝違法，除另有減輕或免除其刑之依據未列入本次計算"
                         if under_lo else "")}
    out["caution"] = ("本工具只算加減例之形式範圍（§64-§73），不代為判斷有無加重減輕事由、"
                      "不代為量刑（§57）。累犯（§47）、自首（§62）、未遂（§25Ⅱ）等是否構成，由法官認定後以 "
                      "adjustments 輸入。數罪併罰之定應執行刑（§51）不在本工具範圍。")
    return out
