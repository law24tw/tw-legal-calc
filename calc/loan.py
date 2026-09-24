"""銀行分期利率試算（等額本息 annuity）。三模式：給息算月付／給月付反解實質年利率／手續費換算。"""
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
from .dates import CalcError

D = Decimal
def _d(x): return D(str(x))
def _r(x, n=2): return float(D(x).quantize(D(1).scaleb(-n), rounding=ROUND_HALF_UP))
def _rate(r):
    r = _d(r)
    return r / 100 if r > 1 else r


def _pmt(p: D, i: D, n: int) -> D:
    if i == 0:
        return p / n
    f = (1 + i) ** n
    return p * i * f / (f - 1)


def _schedule(p: D, i: D, n: int, pay: D):
    bal, rows, ti = p, [], D(0)
    for k in range(1, n + 1):
        interest = bal * i
        principal = pay - interest
        if k == n:
            principal, pay_k = bal, bal + interest
        else:
            pay_k = pay
        bal -= principal
        ti += interest
        rows.append({"n": k, "payment": _r(pay_k), "interest": _r(interest),
                     "principal": _r(principal), "balance": _r(max(bal, D(0)))})
    return rows, ti


def installment(mode="pmt", principal=0, months=0, apr=None, payment=None, fee=0,
                schedule=False, **_):
    p, n = _d(principal), int(months)
    if p <= 0 or n <= 0:
        raise CalcError("本金與期數均須大於 0")
    if n > 600:
        raise CalcError("期數過大（>50年）")

    if mode == "pmt":
        if apr is None:
            raise CalcError("mode=pmt 需給 apr（名目年利率）")
        r = _rate(apr); i = r / 12
        pay = _pmt(p, i, n)
        note = "等額本息：每期應繳 = 本金 × 月利率 ÷ (1 −(1+月利率)^-期數)"
    else:
        if mode == "addon":
            total_fee = _d(fee)
            pay = (p + total_fee) / n
            note = f"手續費/利息總額 {_r(total_fee)} 元平均攤入 {n} 期，再以 IRR 反解實質年利率"
        elif mode == "rate":
            if payment is None:
                raise CalcError("mode=rate 需給 payment（每期應繳）")
            pay = _d(payment)
            note = "由每期應繳以二分法解月 IRR，再年化為實質年利率"
        else:
            raise CalcError("mode 需為 pmt / rate / addon")
        if pay * n <= p:
            i = D(0)
        else:
            lo, hi = D(0), D("0.5")
            for _k in range(200):
                mid = (lo + hi) / 2
                if _pmt(p, mid, n) < pay:
                    lo = mid
                else:
                    hi = mid
            i = (lo + hi) / 2
        r = i * 12

    rows, total_interest = _schedule(p, i, n, pay)
    out = {"mode": mode, "principal": _r(p), "months": n,
           "monthly_rate": _r(i, 8), "apr": _r(r * 100, 4),
           "apr_decimal": float(r),
           "payment": _r(pay), "total_payment": _r(sum(_d(x["payment"]) for x in rows)),
           "total_interest": _r(total_interest), "formula": note,
           "note": "實質年利率＝月利率×12（名目年利率法）；若需 APY 複利年化，另計 (1+i)^12−1"}
    out["apy"] = _r(((1 + i) ** 12 - 1) * 100, 4)
    if schedule:
        out["schedule"] = rows
    else:
        out["schedule_sample"] = rows[:3] + (["..."] if n > 6 else []) + rows[-3:]
    return out


# ── 借款還款餘額計算表 ────────────────────────────────
# 對照司法院辦案小工具 Excel 專區同名工具之公開說明實作。
# 案型：原告陸續借款、被告陸續還款，爭執是否已清償或溢償。
# 兩點實作要求：
#   ① 四捨五入只能在最後一次結算時使用，中間小結不可捨入（逐次捨入會累積成可見誤差）——
#     本實作全程 Decimal，只在輸出時 quantize。
#   ② YEARFRAC 參數 0/1/2/3/4＝美國30/360、實際天數、實際/360、實際/365、歐洲30/360；
#     預設用 1（實際天數）：閏年按 365 計會少算 1 天、對借款人不利。
from calendar import isleap
from datetime import date as _date
from .dates import to_date, roc


def _y30(d1: _date, d2: _date, european: bool) -> float:
    d1d, d2d = d1.day, d2.day
    if european:
        d1d, d2d = min(d1d, 30), min(d2d, 30)
    else:                                     # NASD / 美國 30/360
        if d1d == 31:
            d1d = 30
        if d2d == 31 and d1d == 30:
            d2d = 30
    return ((d2.year - d1.year) * 360 + (d2.month - d1.month) * 30 + (d2d - d1d)) / 360.0


def yearfrac(d1: _date, d2: _date, basis: int = 1) -> float:
    """Excel YEARFRAC 相容。basis 0=美30/360 1=實際天數 2=實際/360 3=實際/365 4=歐30/360。"""
    if d2 < d1:
        d1, d2 = d2, d1
    days = (d2 - d1).days
    if basis == 0:
        return _y30(d1, d2, False)
    if basis == 4:
        return _y30(d1, d2, True)
    if basis == 2:
        return days / 360.0
    if basis == 3:
        return days / 365.0
    # basis 1：實際天數（actual/actual）
    if d2.year - d1.year > 1 or (d2.year - d1.year == 1 and (d2.month, d2.day) > (d1.month, d1.day)):
        yrs = range(d1.year, d2.year + 1)
        denom = sum(366 if isleap(y) else 365 for y in yrs) / len(list(yrs))
    else:
        denom = 365.0
        for y in (d1.year, d2.year):
            if isleap(y):
                feb29 = _date(y, 2, 29)
                if d1 <= feb29 <= d2:
                    denom = 366.0
                    break
    return days / denom


def balance(events=None, apr=0, basis=1, compound=True, **_):
    """借款還款餘額計算表。

    events: [{date, lend, repay}]（lend＝借出／repay＝還款，同日可同列）
    回傳逐列明細與期末餘額；餘額為負＝溢償。
    """
    evs = []
    for i, e in enumerate(events or [], 1):
        d = to_date(e.get("date"))
        evs.append({"no": i, "date": d, "lend": _d(e.get("lend", 0) or 0),
                    "repay": _d(e.get("repay", 0) or 0)})
    if not evs:
        raise CalcError("需給 events（借款／還款明細）")
    evs.sort(key=lambda x: x["date"])                 # 從最舊到最新排序
    r = _rate(apr)
    bal, interest_acc, rows = D(0), D(0), []
    prev = evs[0]["date"]
    for i, e in enumerate(evs, 1):
        yf = D(str(yearfrac(prev, e["date"], int(basis)))) if e["date"] > prev else D(0)
        base = bal if compound else (bal - interest_acc)
        seg_int = base * r * yf
        interest_acc += seg_int
        bal = bal + seg_int + e["lend"] - e["repay"]
        rows.append({"no": i, "date": roc(e["date"]), "days": (e["date"] - prev).days,
                     "yearfrac": round(float(yf), 8),
                     "lend": _r(e["lend"]), "repay": _r(e["repay"]),
                     "interest": _r(seg_int), "balance": _r(bal)})
        prev = e["date"]
    return {
        "rows": rows, "count": len(rows),
        "apr": float(r), "basis": int(basis),
        "basis_label": {0: "美國30/360", 1: "實際天數", 2: "實際/360", 3: "實際/365",
                        4: "歐洲30/360"}.get(int(basis), "?"),
        "compound": bool(compound),
        "total_lend": _r(sum(e["lend"] for e in evs)),
        "total_repay": _r(sum(e["repay"] for e in evs)),
        "total_interest": _r(interest_acc),
        "final_balance": _r(bal),
        "verdict": ("被告尚欠 %s 元" % _r(bal)) if bal > 0 else
                   ("已清償並溢償 %s 元" % _r(-bal)) if bal < 0 else "恰好清償",
        "precision_note": "全程 Decimal 累算，僅輸出時四捨五入；中間小結不得捨入（逐次捨入會累積成可見誤差）",
        "compound_caution": "compound=true 係將利息滾入累計本金；民法§207 原則上禁止複利（利息不得滾入原本再生利息），"
                            "除當事人另有約定或商業上習慣。爭執時請改 compound=false 分列本息。",
        "basis_advice": "閏年按365計會少算1天、對借款人不利；建議 basis=1（實際天數）",
    }
