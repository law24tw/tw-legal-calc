"""民國日期與期間基礎工具。

所有對外參數一律吃民國 YYYMMDD（如 1150924），也接受西元 YYYY-MM-DD / YYYYMMDD。
民法§120Ⅱ 始日不算入為原則，但各工具依其自身說明覆寫（例：利息起迄均計入）。
"""
from __future__ import annotations
from datetime import date, timedelta


class CalcError(ValueError):
    pass


def to_date(v) -> date:
    if isinstance(v, date):
        return v
    s = str(v).strip().replace("/", "").replace("-", "").replace(".", "")
    if not s.isdigit():
        raise CalcError(f"日期格式不合：{v}（需 民國YYYMMDD 或 西元YYYYMMDD）")
    if len(s) == 7:                       # 民國 1150924
        y, m, d = int(s[:3]) + 1911, int(s[3:5]), int(s[5:7])
    elif len(s) == 6:                     # 民國 990924
        y, m, d = int(s[:2]) + 1911, int(s[2:4]), int(s[4:6])
    elif len(s) == 8:                     # 西元 20260924
        y, m, d = int(s[:4]), int(s[4:6]), int(s[6:8])
    else:
        raise CalcError(f"日期長度不合：{v}")
    try:
        return date(y, m, d)
    except ValueError as e:
        raise CalcError(f"日期不存在：{v}（{e}）")


def roc(d: date) -> str:
    return f"{d.year - 1911}.{d.month}.{d.day}"


def roc8(d: date) -> str:
    return f"{d.year - 1911:03d}{d.month:02d}{d.day:02d}"


def add_months(d: date, n: int) -> date:
    """加 n 個月；當月無該日者取該月末日（民法§121Ⅱ但書之精神）。"""
    y, m = d.year + (d.month - 1 + n) // 12, (d.month - 1 + n) % 12 + 1
    for day in range(d.day, 27, -1):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    return date(y, m, d.day)


def add_years(d: date, n: int) -> date:
    try:
        return d.replace(year=d.year + n)
    except ValueError:            # 2/29
        return d.replace(year=d.year + n, day=28)


def ymd_between(start: date, end_exclusive: date):
    """從 start 到 end_exclusive（不含）折算 X年Y月Z日。"""
    if end_exclusive < start:
        raise CalcError("終止日早於起算日")
    y = 0
    while add_years(start, y + 1) <= end_exclusive:
        y += 1
    anchor = add_years(start, y)
    m = 0
    while add_months(anchor, m + 1) <= end_exclusive:
        m += 1
    anchor2 = add_months(anchor, m)
    return y, m, (end_exclusive - anchor2).days


def year_basis(start: date, end_inclusive: date):
    """給付基數（以年為單位，起迄均計入）。

    足年：start 起算，至「次年相當日之前一日」為滿 1 年（例 111.3.10~112.3.9）。
    不足年：殘日 / 該殘期所在年度之總日數。
    回傳 (足年數, 殘日, 該年度總日數, 基數Decimal)
    """
    from decimal import Decimal
    if end_inclusive < start:
        raise CalcError("終止日早於起算日")
    n = 0
    while add_years(start, n + 1) - timedelta(days=1) <= end_inclusive:
        n += 1
    rem_start = add_years(start, n)
    rem_days = (end_inclusive - rem_start).days + 1
    if rem_days < 0:
        rem_days = 0
    denom = (add_years(rem_start, 1) - rem_start).days
    basis = Decimal(n) + (Decimal(rem_days) / Decimal(denom) if rem_days else Decimal(0))
    return n, rem_days, denom, basis
