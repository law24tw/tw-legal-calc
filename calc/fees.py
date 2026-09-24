"""司法規費試算（民事）。

核心觀念（2026-09-24 查證訂正，見 data/court_fees.yaml meta.key_insight）：
  「114/1/1 新法」不是民訴§77-13 修正——§77-13 自 112/11/29 起未變（十萬元以下 1,000 元）。
  1,500 來自各高等法院依 §77-27 報請司法院核准之**加徵**，且加徵是**累進三級**
  （十萬以下 +5/10、逾十萬至一千萬 +3/10、逾一千萬 +1/10），不是一律 1.5 倍。
  驗算：一審 1000×1.5＝1,500；二三審 §77-16 先×1.5 得 1,500、再依提高標準§3 ×1.5 得 2,250。
  ⚠ 各高等法院轄區標準各自發布，須先依**原審法院**定轄區。本版只收臺灣高等法院轄區。
"""
from __future__ import annotations
import math, os
from decimal import Decimal, ROUND_HALF_UP
import yaml
from .dates import CalcError

D = Decimal
_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_PATH = os.path.join(_HERE, "data", "court_fees.yaml")
_C: dict = {}
# 9/24 已補金門分院標準（pcode B0010059），逐條比對比例與臺灣高等法院部完全相同，
# 故不再拒算金門、連江。僅保留提示：涉第二審訴之變更/追加/§54起訴/反訴者，兩部文字有別，請回查原文。
KINMEN = {"福建金門地方法院", "福建連江地方法院", "金門地方法院", "連江地方法院"}


def _cfg():
    mt = os.path.getmtime(_PATH)
    if _C.get("_mtime") != mt:
        with open(_PATH, encoding="utf-8") as f:
            _C.clear(); _C.update(yaml.safe_load(f)); _C["_mtime"] = mt
    return _C


def _r(x, n=0):
    return float(D(str(x)).quantize(D(1).scaleb(-n), rounding=ROUND_HALF_UP))


def _tier_fee(amount: D, tier) -> D:
    """該級距內的 §77-13 費額。"""
    lo, hi = D(tier["from"]), (D(tier["to"]) if tier["to"] is not None else None)
    if tier["mode"] == "flat":
        return D(tier["amount"]) if amount >= 0 else D(0)
    top = amount if hi is None else min(amount, hi)
    part = top - lo
    if part <= 0:
        return D(0)
    units = math.ceil(part / D(10000))            # 畸零之數不滿萬元者，以萬元計算
    return D(units) * D(tier["rate"])


def _surcharge_rate(tier_lo: D, ver) -> D:
    for s in ver["property_tiers"]:
        s_lo, s_hi = D(s["from"]), (D(s["to"]) if s["to"] is not None else None)
        if tier_lo >= s_lo and (s_hi is None or tier_lo < s_hi):
            return D(str(s["rate"]))
    return D(0)


def court_fee(kind="property", amount=0, instance=1, paid=0, surcharge_version="114",
              court=None, labor=False, apply_surcharge=True, **_):
    """民事裁判費試算。

    kind: property 因財產權起訴｜non_property 非因財產權｜retrial_ruling 對確定裁定聲請再審
          ｜appeal_ruling 抗告/再為抗告｜mediation 聲請調解｜execution 強制執行
    instance: 1=第一審；2/3=第二、三審（§77-16Ⅰ 加徵十分之五）
    """
    c = _cfg()
    kinmen = bool(court and court in KINMEN)
    vers = c["surcharge"]["versions"]
    ver = vers.get(str(surcharge_version))
    if ver is None:
        raise CalcError(f"未知加徵版本 {surcharge_version}；可用：{list(vers)}")
    if ver.get("status") == "needs_data":
        raise CalcError(f"加徵版本 {surcharge_version} 尚未備料：{ver.get('note')}")

    amt = D(str(amount or 0))
    steps, base = [], D(0)

    if kind in ("property", "因財產權"):
        bp = c["base_property"]
        segs = []
        for t in bp["tiers"]:
            f = _tier_fee(amt, t)
            if f > 0:
                sr = _surcharge_rate(D(t["from"]), ver) if apply_surcharge else D(0)
                segs.append({"label": t["label"], "base": _r(f),
                             "surcharge_rate": float(sr), "with_surcharge": _r(f * (1 + sr))})
                base += f
        steps = segs
        sub = sum(D(str(s["with_surcharge"])) for s in segs)
        basis = [bp["basis"], "提高徵收額數標準§2"]
    elif kind in ("non_property", "非因財產權"):
        base = D(c["flat_fees"]["non_property"]["amount"])
        sr = D(str(ver["non_property"])) if apply_surcharge else D(0)
        sub = base * (1 + sr)
        steps = [{"label": "非因財產權而起訴", "base": _r(base),
                  "surcharge_rate": float(sr), "with_surcharge": _r(sub)}]
        basis = ["民訴§77-14Ⅰ", "提高徵收額數標準§2後段"]
    elif kind in ("retrial_ruling", "appeal_ruling"):
        key = "retrial_ruling" if kind == "retrial_ruling" else "appeal_ruling"
        base = D(c["flat_fees"][key]["amount"])
        sr = D(str(ver[key])) if apply_surcharge else D(0)
        sub = base * (1 + sr)
        steps = [{"label": c["flat_fees"][key]["label"], "base": _r(base),
                  "surcharge_rate": float(sr), "with_surcharge": _r(sub)}]
        basis = [c["flat_fees"][key]["basis"], "提高徵收額數標準§4"]
        instance = 1
    elif kind in ("mediation", "聲請調解"):
        m = c["mediation"]
        hit = next((t for t in m["tiers"]
                    if amt >= D(t["from"]) and (t["to"] is None or amt < D(t["to"]))), None)
        base = D(hit["amount"]) if hit else D(0)
        sub = base
        steps = [{"label": hit["label"] if hit else "-", "base": _r(base),
                  "surcharge_rate": 0.0, "with_surcharge": _r(base)}]
        basis = [m["basis"]]
        instance = 1
    elif kind in ("execution", "強制執行"):
        e = c["execution"]
        if amt < D(e["exempt_below"]):
            base = sub = D(0)
            steps = [{"label": f"未滿 {e['exempt_below']} 元免徵執行費", "base": 0.0,
                      "surcharge_rate": 0.0, "with_surcharge": 0.0}]
        else:
            units = math.ceil(amt / D(e["round_up_to"]))      # 不滿百元以百元計
            base = D(units) * D(str(e["rate_per_100"]))
            sr = D(str(ver["execution"])) if apply_surcharge else D(0)
            sub = base * (1 + sr)
            steps = [{"label": "每百元收七角", "base": _r(base, 2),
                      "surcharge_rate": float(sr), "with_surcharge": _r(sub)}]
        basis = [e["basis"], "提高徵收額數標準§6（加徵七分之一）"]
        instance = 1
    else:
        raise CalcError("kind 需為 property／non_property／retrial_ruling／appeal_ruling／mediation／execution")

    out = {"kind": kind, "amount": _r(amt), "instance": instance,
           "surcharge_version": surcharge_version, "surcharge_applied": bool(apply_surcharge),
           "segments": steps, "base_fee": _r(base), "fee_after_surcharge": _r(sub)}

    if instance in (2, 3) and kind in ("property", "非因財產權", "non_property"):
        ap = c["appeal"]
        mult = D(str(ap["multiplier"]))
        base2 = base * mult
        if apply_surcharge:
            if kind in ("property", "因財產權"):
                sub = sum(D(str(s["base"])) * mult * (1 + D(str(s["surcharge_rate"])))
                          for s in steps)
            else:
                sub = base2 * (1 + D(str(ver["non_property"])))
        else:
            sub = base2
        out.update({"appeal_multiplier": float(mult), "base_fee_appeal": _r(base2),
                    "fee_after_surcharge": _r(sub),
                    "appeal_note": ap["label"], "appeal_exempt_note": ap["exempt_note"]})
        basis.append("民訴§77-16Ⅰ"); basis.append("提高徵收額數標準§3")

    total = sub
    if labor:
        lb = c["labor"]
        deferred = total * D(str(lb["defer_ratio"]))
        out.update({"labor_case": True, "labor_basis": lb["basis"],
                    "deferred": _r(deferred), "payable_now": _r(total - deferred),
                    "labor_note": lb["label"] + "（暫免非免除，敗訴時仍應徵收）"})
        basis.append(lb["basis"])
        total = total - deferred

    if kinmen:
        out["region"] = "福建高等法院金門分院轄區（pcode B0010059）"
        out["region_caveat"] = ("加徵比例與臺灣高等法院部相同，已逐條比對；"
                                "惟第二審訴之變更、追加、民訴§54起訴補徵、反訴四種情形，"
                                "金門分院部§3Ⅲ有明文而臺灣高等法院部無，涉此請回查原文。")
    out.update({"total_due": _r(total), "paid": _r(paid),
                "to_supplement": _r(max(D(0), total - D(str(paid or 0)))),
                "refund": _r(max(D(0), D(str(paid or 0)) - total)),
                "basis": basis,
                "region_note": ver["regions_note"].strip(),
                "caution": "加徵標準各高等法院轄區各自發布，本版僅臺灣高等法院轄區；"
                           "算裁判費前先依原審法院定轄區"})
    return out
