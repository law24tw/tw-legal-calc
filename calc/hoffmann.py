"""霍夫曼式（單利）中間利息扣除。

原理：定期給付具有時間價值，以法定利率年息5%計，現在的100元一年後會變成105元。
故定期給付要「提前」且「一次」清償時，須扣除「未來給付」部分之中間利息。
PV = Σ A / (1 + r × n)   n＝該期距折現基準之期數
首期是否扣除中間利息：實務多數說為「否」（第一期到期即給付，無中間利息可扣）。
"""
from __future__ import annotations
from decimal import Decimal, ROUND_HALF_UP
from .dates import to_date, roc, add_months, CalcError

D = Decimal
def _d(x): return D(str(x))
def _r(x, n=0): return float(D(x).quantize(D(1).scaleb(-n), rounding=ROUND_HALF_UP))
def _rate(r):
    r = _d(r)
    return r / 100 if r > 1 else r


def lump_sum(amount=0, unit="year", periods=0, rate=0.05, persons=1, share_pct=100,
             deduct_first=False, **_):
    """霍夫曼一次給付試算：每期 amount 元、共 periods 期（可含小數）。"""
    a = _d(amount) * _d(persons) * _d(share_pct) / 100
    r = _rate(rate)
    per = r if unit == "year" else r / 12
    p = _d(periods)
    if p < 0:
        raise CalcError("給付期數不可為負")
    full = int(p)
    frac = p - full
    if full > 12000:
        raise CalcError("期數過大")
    total = D(0)
    for k in range(1, full + 1):
        n = D(k) if deduct_first else D(k - 1)
        total += a / (1 + per * n)
    if frac > 0:
        n = D(full + 1) if deduct_first else D(full)
        total += a * frac / (1 + per * n)
    return {"per_period_amount": _r(a, 2), "unit": "年" if unit == "year" else "月",
            "periods_total": float(p), "periods_full": full, "partial_ratio": float(frac),
            "annual_rate": float(r), "per_period_rate": float(per),
            "deduct_first": bool(deduct_first),
            "formula": "Σ 每期給付 ÷ (1 + 每期利率 × 期數)" + ("" if deduct_first else "；首期不扣中間利息（實務多數說）"),
            "amount": _r(total), "amount_exact": str(total),
            "basis": "民法§203 法定利率5%；霍夫曼式單利折現"}


def pv_periodic(monthly=0, start=None, end=None, base=None, rate=0.05,
                deduct_first=False, **_):
    """定期給付折現：A→B 每月給付 M，折現至 S 時點。"""
    A, B, S = to_date(start), to_date(end), to_date(base)
    if B <= A:
        raise CalcError("給付屆滿日須晚於給付開始日")
    m = _d(monthly)
    r = _rate(rate)
    per = r / 12
    rows, total, k = [], D(0), 0
    while True:
        pay = add_months(A, k)
        if pay >= B:
            break
        if k > 1500:
            raise CalcError("給付期數過大（>125年）")
        n_months = (pay.year - S.year) * 12 + (pay.month - S.month)
        if pay.day < S.day:
            n_months -= 1
        if n_months < 0:
            n_months = 0                 # 折現基準日之前的給付不折現
        if not deduct_first and n_months > 0:
            n_months -= 1
        pv = m / (1 + per * D(n_months))
        total += pv
        if k < 6 or pay >= add_months(B, -6):
            rows.append({"n": k + 1, "date": roc(pay), "discount_months": n_months, "pv": _r(pv, 2)})
        k += 1
    return {"monthly": _r(m, 2), "start": roc(A), "end": roc(B), "base": roc(S),
            "annual_rate": float(r), "periods": k,
            "formula": "每期給付 ÷ (1 + 年利率÷12 × 折現月數)，逐期加總；折現基準日前之給付不折現",
            "deduct_first": bool(deduct_first),
            "sample_rows": rows, "amount": _r(total), "amount_exact": str(total),
            "note": "折現月數以曆月計；若當事人主張逐日折現，請改用 calc.eval 另算並敘明",
            "basis": "民法§192Ⅱ、§203；霍夫曼式單利折現"}
