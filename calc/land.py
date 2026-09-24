"""土地／共有類：應有部分比例、分割面積地價、維持共有、合併後應有部分。"""
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
from fractions import Fraction
from math import gcd
from .dates import CalcError

D = Decimal
def _d(x): return D(str(x))
def _r(x, n=2):
    if isinstance(x, Fraction):
        x = D(x.numerator) / D(x.denominator)
    return float(D(x).quantize(D(1).scaleb(-n), rounding=ROUND_HALF_UP))
def _fr(o, i=0):
    num, den = o.get("num", 1), o.get("den", 1)
    try:
        f = Fraction(int(num), int(den))
    except (ValueError, ZeroDivisionError, TypeError):
        raise CalcError(f"第{i}列應有部分不合法：{num}/{den}")
    return f


def share_ratio(owners=None, **_):
    owners = owners or []
    if not owners:
        raise CalcError("需給 owners（共有人清單）")
    fr = [_fr(o, i + 1) for i, o in enumerate(owners)]
    lcm = 1
    for f in fr:
        lcm = lcm * f.denominator // gcd(lcm, f.denominator)
    total = sum(fr, Fraction(0))
    rows = [{"no": i + 1, "name": o.get("name", f"共有人{i+1}"),
             "share": f"{f.numerator}/{f.denominator}",
             "normalized": f"{f.numerator * (lcm // f.denominator)}/{lcm}",
             "pct": _r(f * 100, 6)}
            for i, (o, f) in enumerate(zip(owners, fr))]
    return {"rows": rows, "common_denominator": lcm,
            "total": f"{total.numerator}/{total.denominator}",
            "total_pct": _r(total * 100, 6),
            "is_whole": total == 1,
            "check": "合計等於 1，應有部分完整" if total == 1
                     else f"⚠ 合計為 {total.numerator}/{total.denominator}，不等於 1，請覆核登記謄本"}


def partition(parcels=None, owners=None, **_):
    """土地分割共有物：面積與地價之試算。"""
    parcels = parcels or []
    owners = owners or []
    if not parcels:
        raise CalcError("需給 parcels（土地資料）")
    pmap = {}
    for i, p in enumerate(parcels, 1):
        lot = str(p.get("lot", f"地號{i}"))
        area, up = _d(p.get("area_m2", 0)), _d(p.get("unit_price", 0))
        pmap[lot] = {"lot": lot, "area_m2": _r(area), "unit_price": _r(up),
                     "total_value": _r(area * up)}
    rows = []
    for i, o in enumerate(owners, 1):
        lot = str(o.get("lot", list(pmap)[0]))
        if lot not in pmap:
            raise CalcError(f"第{i}列地號 {lot} 不在土地資料中")
        f = _fr(o, i)
        area = _d(pmap[lot]["area_m2"]) * f.numerator / f.denominator
        val = _d(pmap[lot]["unit_price"]) * area
        rows.append({"no": i, "lot": lot, "name": o.get("name", f"共有人{i}"),
                     "share": f"{f.numerator}/{f.denominator}",
                     "entitled_area_m2": _r(area, 4), "entitled_value": _r(val)})
    return {"parcels": list(pmap.values()),
            "total_area_m2": _r(sum(_d(p["area_m2"]) for p in pmap.values()), 4),
            "total_value": _r(sum(_d(p["total_value"]) for p in pmap.values())),
            "owners": rows,
            "sum_entitled_area_m2": _r(sum(_d(r["entitled_area_m2"]) for r in rows), 4),
            "sum_entitled_value": _r(sum(_d(r["entitled_value"]) for r in rows)),
            "formula": "應有面積 = 土地面積 × 應有部分；應有價額 = 公告土地現值 × 應有面積"}


def keep_share(area_m2=0, unit_price=0, owners=None, **_):
    """土地單筆部分維持共有：分割後應有部分 = 原應有部分 ÷ 維持共有者合計。"""
    owners = owners or []
    if not owners:
        raise CalcError("需給 owners（維持共有之人）")
    fr = [_fr(o, i + 1) for i, o in enumerate(owners)]
    tot = sum(fr, Fraction(0))
    if tot == 0:
        raise CalcError("維持共有者應有部分合計為 0")
    rows = []
    for i, (o, f) in enumerate(zip(owners, fr), 1):
        nf = f / tot
        area = _d(area_m2) * nf.numerator / nf.denominator
        rows.append({"no": i, "title": o.get("title", ""), "name": o.get("name", f"共有人{i}"),
                     "share_before": f"{f.numerator}/{f.denominator}",
                     "share_after": f"{nf.numerator}/{nf.denominator}",
                     "entitled_area_m2": _r(area, 4),
                     "entitled_value": _r(_d(unit_price) * area)})
    return {"area_m2": _r(_d(area_m2), 4), "unit_price": _r(_d(unit_price)),
            "keep_total_share_before": f"{tot.numerator}/{tot.denominator}",
            "rows": rows,
            "formula": "分割後應有部分 = 該人原應有部分 ÷ 維持共有者原應有部分合計（合計後為 1）",
            "basis": ["民法§824Ⅳ", "民法§824-1"]}


def merge_share(rows=None, **_):
    """土地數筆合併後應有部分 = 該人應有面積合計 ÷ 全部面積合計。"""
    rows = rows or []
    if not rows:
        raise CalcError("需給 rows（各筆土地與原應有部分）")
    detail, total_area, by_name = [], D(0), {}
    for i, r in enumerate(rows, 1):
        f = _fr(r, i)
        area = _d(r.get("area_m2", 0))
        ent = area * f.numerator / f.denominator
        name = r.get("name", f"共有人{i}")
        detail.append({"no": i, "name": name, "lot": r.get("lot", ""),
                       "share_before": f"{f.numerator}/{f.denominator}",
                       "area_m2": _r(area, 4), "entitled_area_m2": _r(ent, 4)})
        by_name[name] = by_name.get(name, D(0)) + ent
        total_area += area
    if total_area == 0:
        raise CalcError("面積合計為 0")
    after = [{"name": n, "entitled_area_m2": _r(a, 4),
              "share_after": str(Fraction(int(a * 10**6), int(total_area * 10**6)).limit_denominator(10**9)),
              "share_after_pct": _r(a / total_area * 100, 6)}
             for n, a in by_name.items()]
    return {"rows": detail, "total_area_m2": _r(total_area, 4), "after": after,
            "formula": "合併後應有部分 = 該人各筆應有面積合計 ÷ 合併後總面積",
            "note": "分數已約分至最簡；登記時仍應以地政事務所核算之分母為準"}
