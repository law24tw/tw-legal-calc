"""金錢類：利息／違約金、折舊、相當租金不當得利。"""
from __future__ import annotations
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from .dates import to_date, roc, add_years, year_basis, ymd_between, CalcError

D = Decimal
def _d(x): return D(str(x))
def _r(x, n=0): return float(D(x).quantize(D(1).scaleb(-n), rounding=ROUND_HALF_UP))
def _rate(r):
    r = _d(r)
    return r / 100 if r > 1 else r          # 5 與 0.05 同義


# ── 利息及違約金試算 ──────────────────────────────────
def interest_penalty(principal=0, rate=0, start=None, end=None, kind="interest", monthly=None, **_):
    s, e = to_date(start), to_date(end)
    n, rem, denom, basis = year_basis(s, e)
    out = {"start": roc(s), "end": roc(e),
           "rule": "給付期間起算日及終止日均計入；足年部分算足年數，不足年部分＝殘日÷該年度總日數",
           "basis_years": {"full": n, "remainder_days": rem, "denominator": denom,
                           "value": float(basis),
                           "text": (f"{rem}/{denom}" if (rem and not n) else
                                    f"{n}又{rem}/{denom}" if rem else str(n))}}
    if kind == "penalty_monthly":
        if monthly is None:
            raise CalcError("kind=penalty_monthly 需給 monthly（按月給付金額）")
        y, m, _d0 = ymd_between(s, e + timedelta(days=1))   # 起迄均計入
        months = y * 12 + m
        out.update({"kind": "按月給付之違約金", "monthly": float(_d(monthly)), "months": months,
                    "formula": "按月給付金額 × (給付期間之年×12 + 給付期間之月【不足一月者不計】)",
                    "amount": _r(_d(monthly) * months)})
        return out
    r = _rate(rate)
    amt = _d(principal) * basis * r
    out.update({"kind": "利息", "principal": float(_d(principal)), "rate": float(r),
                "formula": "計算本金 × 給付基數(以年為單位) × 年息",
                "amount": _r(amt), "amount_exact": str(amt)})
    return out


def penalty_items(items=None, **_):
    """多列請求項目合併試算（本金/利息/違約金）。"""
    items = items or []
    rows, total = [], D(0)
    for i, it in enumerate(items, 1):
        k = it.get("kind", "principal")
        if k in ("principal", "本金"):
            a = _d(it.get("amount", 0))
            rows.append({"no": i, "kind": "本金", "amount": _r(a)})
        elif k in ("interest", "利息"):
            sub = interest_penalty(it.get("amount", 0), it.get("rate", 0), it["start"], it["end"])
            a = _d(sub["amount_exact"]); rows.append({"no": i, "kind": "利息", "detail": sub, "amount": _r(a)})
        elif k in ("penalty", "違約金"):
            sub = interest_penalty(0, 0, it["start"], it["end"], "penalty_monthly", it.get("monthly"))
            a = _d(sub["amount"]); rows.append({"no": i, "kind": "違約金", "detail": sub, "amount": _r(a)})
        else:
            raise CalcError(f"第{i}列 kind 不明：{k}")
        total += a
    return {"rows": rows, "count": len(rows), "total": _r(total)}


# ── 折舊自動試算表 ────────────────────────────────────
_LIFE_LABEL = {3: "機械腳踏車", 4: "運輸業用客車、貨車", 5: "非運輸業用客車、貨車"}

def depreciation(cost=0, years=0, used_years=0, used_months=0, method="average", residual=None, **_):
    cost = _d(cost); n = int(years)
    if cost <= 0 or n <= 0:
        raise CalcError("購入成本與耐用年數均須大於 0")
    um = int(used_years) * 12 + int(used_months)        # 月數由呼叫端輸入；畸零日數依查核準則§95⑥進位為一月
    if method in ("average", "平均法"):
        res = _d(residual) if residual is not None else cost / (n + 1)
        per_year = (cost - res) / n
        full_y, rem_m = divmod(um, 12)
        full_y = min(full_y, n)
        acc = per_year * full_y + (per_year * rem_m / 12 if full_y < n else 0)
        acc = min(acc, cost - res)
        rate = per_year / cost if cost else D(0)
        formula = (f"每年折舊 =(成本 {cost} − 殘價 {res}) ÷ 耐用年數 {n}；未滿一年按月數比例計，"
                   "不滿一月者以一月計（查核準則§95第6款），請將畸零日數進位為一月後再輸入 used_months")
    elif method in ("declining", "定率遞減法"):
        res = _d(residual) if residual is not None else cost / (n + 1)
        rate = 1 - D(str((float(res) / float(cost)) ** (1.0 / n)))
        book, acc = cost, D(0)
        for _i in range(min(um // 12, n)):
            dep = book * rate; acc += dep; book -= dep
        rem_m = um - (um // 12) * 12
        if um // 12 < n and rem_m:
            acc += book * rate * rem_m / 12
        formula = f"折舊率 = 1 − (殘價÷成本)^(1÷{n})；每年折舊 = 期初帳面 × 折舊率"
    else:
        raise CalcError("method 需為 average（平均法）或 declining（定率遞減法）")
    pv = cost - acc
    return {"method": "平均法" if method in ("average", "平均法") else "定率遞減法",
            "life_years": n, "life_label": _LIFE_LABEL.get(n, "自填"),
            "cost": _r(cost), "residual": _r(res, 2), "used": f"{used_years}年{used_months}月",
            "depreciation_rate": _r(rate, 6), "formula": formula,
            "accumulated_depreciation": _r(acc), "present_value": _r(pv),
            "acc_over_cost": _r(acc / cost, 4), "pv_over_cost": _r(pv / cost, 4),
            "basis": ["所得稅法§54第2項（應預估殘值，以減除殘值後之餘額為計算基礎）",
                      "營利事業所得稅查核準則§95第6款（未滿一年按月比例；不滿一月以月計）",
                      "固定資產耐用年數表"],
            "residual_note": "殘價＝成本÷(耐用年數+1) 為法院車損折舊實務慣用算法，非查核準則或所得稅法明文；"
                             "當事人有爭執時可改以 residual 參數輸入"}


# ── 相當租金不當得利 ──────────────────────────────────
def unjust_rent(declared_price=0, area_m2=0, rate=0, start=None, end=None, num=1, den=1, **_):
    s, e = to_date(start), to_date(end)
    n, rem, denom, basis = year_basis(s, e)
    r = _rate(rate); share = _d(num) / _d(den)
    annual = _d(declared_price) * _d(area_m2) * r
    amount = annual * basis * share
    monthly = annual / 12 * share
    return {"start": roc(s), "end": roc(e),
            "declared_total_price": _r(_d(declared_price) * _d(area_m2)),
            "rate": float(r), "share": f"{num}/{den}",
            "basis_years": {"full": n, "remainder_days": rem, "denominator": denom, "value": float(basis)},
            "formula": "申報地價 × 占用面積 × 年息 × 給付基數 × 原告應有部分",
            "amount": _r(amount), "monthly_amount": _r(monthly),
            "caution": "年息係法官裁量事項（土地法§97Ⅰ上限為申報總地價年息10%、§105準用），本工具不代為裁量"}
