"""經過時間試算（司法院小工具·通用）。起算日計入、終止日不計。"""
from __future__ import annotations
from decimal import Decimal
from .dates import to_date, roc, add_years, add_months, ymd_between, CalcError


def elapsed(start, end, **_):
    s, e = to_date(start), to_date(end)
    if e < s:
        raise CalcError("終止日早於起算日")
    total_days = (e - s).days                      # 起算日計入、終止日不計
    y, m, d = ymd_between(s, e)
    total_months = y * 12 + m
    mo_anchor = add_months(s, total_months)
    mo_denom = (add_months(mo_anchor, 1) - mo_anchor).days
    yr_anchor = add_years(s, y)
    yr_denom = (add_years(yr_anchor, 1) - yr_anchor).days
    yr_rem = (e - yr_anchor).days
    q = lambda a, b: float(Decimal(a) / Decimal(b)) if b else 0.0
    return {
        "start": roc(s), "end": roc(e),
        "rule": "起算日計入期間計算，終止日不計（民法§120Ⅱ、§121）",
        "total_days": total_days,
        "ymd": {"years": y, "months": m, "days": d, "text": f"{y}年{m}月{d}日"},
        "total_months": total_months,
        "month_remainder": {"days": d, "denominator": mo_denom, "fraction": q(d, mo_denom),
                            "text": f"{total_months}個月又{d}/{mo_denom}"},
        "total_years": y,
        "year_remainder": {"days": yr_rem, "denominator": yr_denom, "fraction": q(yr_rem, yr_denom),
                           "text": f"{y}年又{yr_rem}/{yr_denom}"},
    }
