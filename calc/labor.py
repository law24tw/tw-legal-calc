"""勞動類：資遣費試算、特休日數試算。"""
from __future__ import annotations
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from .dates import to_date, roc, add_years, add_months, ymd_between, CalcError

D = Decimal
def _d(x): return D(str(x))
def _r(x, n=0): return float(D(x).quantize(D(1).scaleb(-n), rounding=ROUND_HALF_UP))


def _service(onboard, leave):
    """年資：回傳 (年, 月, 日, 以年為單位之比例值)。"""
    y, m, d = ymd_between(onboard, leave)
    anchor = add_years(onboard, y)
    denom = (add_years(anchor, 1) - anchor).days
    ratio = D(y) + D((leave - anchor).days) / D(denom)
    return y, m, d, ratio


def avg_wage(wages6=None, method="m1", event=None, **_):
    """平均工資兩算法。wages6＝事由發生前6個月各月工資（由新到舊）。"""
    if not wages6:
        raise CalcError("需給 avg_wage 或 wages6")
    total = sum(_d(w) for w in wages6)
    if method == "m1":
        return total / 6, "算法一：事由發生前6個月工資總額÷6（勞委會83.4.9台83勞動2字第25564號函）"
    e = to_date(event) if event else None
    if not e:
        raise CalcError("算法二需給 event（計算事由發生日）以定期間總日數")
    days = (e - add_months(e, -6)).days
    return total / D(days) * 30, f"算法二：6個月工資總額÷期間總日數{days}×30（最高法院110年度台上字第675號民事判決）"


def severance(avg_wage_amount=None, wages6=None, wage_method="m1", onboard=None, leave=None,
              event=None, scheme="both", switch_date="0940701", **kw):
    avg_wage_amount = kw.get("avg_wage", avg_wage_amount)
    ob, lv = to_date(onboard), to_date(leave)
    ev = to_date(event) if event else lv
    if lv <= ob:
        raise CalcError("離職日須晚於到職日")
    if avg_wage_amount is not None:
        w, wnote = _d(avg_wage_amount), "由參數直接給定"
    else:
        w, wnote = avg_wage(wages6, wage_method, ev)
    sw = to_date(switch_date)
    out = {"onboard": roc(ob), "leave": roc(lv), "event": roc(ev),
           "avg_monthly_wage": _r(w, 2), "avg_wage_note": wnote, "parts": {}}

    def old_part(a, b):
        y, m, d, _ratio = _service(a, b)
        months = y * 12 + m + (1 if d > 0 else 0)      # 未滿一個月者以一個月計
        amt = w * D(months) / 12
        return {"from": roc(a), "to": roc(b), "service": f"{y}年{m}月{d}日",
                "months_counted": months,
                "formula": "每滿1年發給1個月平均工資，未滿1年按比例、未滿1個月以1個月計（勞基法§17）",
                "amount": _r(amt), "cap": None}

    def new_part(a, b):
        y, m, d, ratio = _service(a, b)
        amt = w * ratio / 2
        capped = min(amt, w * 6)
        return {"from": roc(a), "to": roc(b), "service": f"{y}年{m}月{d}日",
                "service_years": _r(ratio, 4),
                "formula": "每滿1年發給1/2個月平均工資，未滿1年按比例，最高6個月平均工資（勞退條例§12）",
                "amount": _r(capped), "uncapped": _r(amt),
                "cap": _r(w * 6), "cap_hit": capped < amt}

    if scheme == "old":
        out["parts"]["舊制"] = old_part(ob, lv)
    elif scheme == "new":
        out["parts"]["新制"] = new_part(ob, lv)
    else:
        if lv <= sw:
            out["parts"]["舊制"] = old_part(ob, lv)
        elif ob >= sw:
            out["parts"]["新制"] = new_part(ob, lv)
        else:
            out["parts"]["舊制"] = old_part(ob, sw)
            out["parts"]["新制"] = new_part(sw, lv)
            out["switch_note"] = f"以 {roc(sw)} 勞退新制施行日切分；實際適用視勞工是否選擇新制而定，本工具僅按日期切分"
    out["total"] = _r(sum(_d(p["amount"]) for p in out["parts"].values()))
    out["basis"] = ["勞基法§17", "勞基法§2④", "勞退條例§12"]
    return out


def annual_leave(onboard=None, leave=None, taken_days=0, daily_wage=None,
                 monthly_wage=None, paid=0, table=None, **_):
    ob, lv = to_date(onboard), to_date(leave)
    if lv <= ob:
        raise CalcError("離職日須晚於到職日")
    tbl = table or {}
    rows_tbl = tbl.get("rows") or [
        {"from_months": 6, "to_months": 12, "days": 3},
        {"from_months": 12, "to_months": 24, "days": 7},
        {"from_months": 24, "to_months": 36, "days": 10},
        {"from_months": 36, "to_months": 60, "days": 14},
        {"from_months": 60, "to_months": 120, "days": 15},
    ]
    over = tbl.get("over_10_years") or {"base_days": 15, "add_per_year": 1, "cap": 30}

    def days_for(start_months: int) -> int:
        for r in rows_tbl:
            if r["from_months"] <= start_months < r["to_months"]:
                return int(r["days"])
        extra = (start_months - 120) // 12 + 1
        return int(min(over["base_days"] + extra * over["add_per_year"], over["cap"]))

    # 2026-09-24 訂正：舊版對離職當年度「按在職比例」折算並掛「施行細則§24-1Ⅱ②」——該款實為
    # 「發給工資之期限：契約終止依第九條發給」，並無比例計給之規定，係捏造法源。
    # 正解（逐字核對現行條文）：
    #   施行細則§24Ⅰ：勞工於符合勞基法§38Ⅰ所定條件時「取得」特別休假之權利 → 期間首日一次取得全額。
    #   勞基法§38Ⅳ：因年度終結或契約終止而未休之日數，雇主應發給工資。
    #   施行細則§24-1Ⅱ①(一)：按勞工未休畢之特別休假日數，乘以其一日工資計發。 → 無比例。
    periods, seg_start, total_days = [], add_months(ob, 6), D(0)
    if seg_start > lv:
        return {"onboard": roc(ob), "leave": roc(lv), "periods": [],
                "note": "在職未滿6個月，尚無特別休假（勞基法§38Ⅰ①）", "entitled_days": 0}
    seg_months, notes = 6, []
    while seg_start < lv:
        seg_end = add_years(ob, 1) if seg_months == 6 else add_years(seg_start, 1)
        full = days_for(seg_months)
        complete = lv >= seg_end
        periods.append({
            "period": f"{roc(seg_start)}~{roc(seg_end - timedelta(days=1))}",
            "acquired_on": roc(seg_start),
            "service_at_start": f"滿{seg_months // 12}年{seg_months % 12}月" if seg_months >= 12 else "滿6個月",
            "entitled_days": full,
            "period_complete": complete,
            "days_counted": float(full),
            "note": "" if complete else
                    "契約終止時本期間尚未屆滿，惟權利已於期間首日取得（施行細則§24Ⅰ），"
                    "未休日數全額計給，不按在職比例折算（勞基法§38Ⅳ、施行細則§24-1Ⅱ①(一)）",
        })
        total_days += D(full)
        seg_start, seg_months = seg_end, (12 if seg_months == 6 else seg_months + 12)
    if seg_start == lv:
        notes.append(f"離職日 {roc(lv)} 恰為下一週年日：若勞工當日仍在職已滿年資，另有 "
                     f"{days_for(seg_months)} 日特休權利，本工具未計入，請依事實認定")
    notes.append("離職結算以週年制（到職日起算）計算法定應休日數。事業單位與勞工協商採曆年制等行使期間者，"
                 "其已給日數不得少於本結果（施行細則§24Ⅱ）")
    unused = total_days - _d(taken_days)
    dw = _d(daily_wage) if daily_wage is not None else (_d(monthly_wage) / 30 if monthly_wage else None)
    res = {"onboard": roc(ob), "leave": roc(lv), "periods": periods,
           "entitled_days": float(total_days), "taken_days": float(_d(taken_days)),
           "unused_days": _r(unused, 1), "notes": notes,
           "basis": ["勞基法§38Ⅰ、Ⅳ", "勞基法施行細則§24Ⅰ（取得時點）",
                     "勞基法施行細則§24-1Ⅱ①(一)（未休日數×一日工資）",
                     "勞基法施行細則§24-1Ⅱ①(二)（一日工資）"]}
    if dw is not None:
        res["daily_wage"] = _r(dw, 2)
        res["unused_wage"] = _r(dw * unused - _d(paid))
        res["formula"] = ("未休日數 × 一日工資 − 已給付工資；一日工資（計月者）＝契約終止前最近一個月"
                          "正常工作時間所得之工資 ÷ 30（施行細則§24-1Ⅱ①(一)(二)）")
    return res
