#!/usr/bin/env python3
"""台灣法律計算工具回歸測試。錨點取自司法院小工具頁面自身「說明」欄之範例。"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import router

F = []
def ck(name, got, want, tol=0.51):
    ok = abs(float(got) - float(want)) <= tol
    print(("✔" if ok else "✘") + f" {name}: got {got} want {want}")
    if not ok:
        F.append(name)

def ck_eq(name, got, want):
    ok = got == want
    print(("✔" if ok else "✘") + f" {name}: got {got!r} want {want!r}")
    if not ok:
        F.append(name)

# ── 錨點1-3：利息給付基數（司法院「利息及違約金試算」說明欄三例）
for a, b, txt in [("1110310", "1110605", "88/365"), ("1120310", "1120605", "88/366"),
                  ("1110310", "1130605", "2又88/365")]:
    r = router.run("interest.penalty", {"principal": 1, "rate": 5, "start": a, "end": b})
    ck_eq(f"基數 {a}~{b}", r["result"]["basis_years"]["text"], txt)

# ── 錨點4：民法§121 期間折算
r = router.run("time.elapsed", {"start": "1150101", "end": "1160101"})
ck_eq("經過時間 1年", r["result"]["ymd"]["text"], "1年0月0日")
ck("經過天數", r["result"]["total_days"], 365, 0)

# ── 錨點5：霍夫曼首期不扣中間利息，與手算級數一致
r = router.run("hoffmann.lump", {"amount": 120000, "unit": "year", "periods": 20})
ck("霍夫曼20年", r["result"]["amount"], sum(120000 / (1 + 0.05 * n) for n in range(20)), 1)

# ── 錨點6：平均法折舊（查核準則§95 殘價＝成本÷(年數+1)）
r = router.run("depreciation", {"cost": 600000, "years": 5, "used_years": 3})
ck("折舊殘價", r["result"]["residual"], 100000)
ck("折舊現值", r["result"]["present_value"], 300000)

# ── 錨點7：特休（勞基法§38）滿5年當年度為15日
r = router.run("leave.annual", {"onboard": "1100101", "leave": "1150401"})
ck_eq("特休滿5年度日數", r["result"]["periods"][-1]["entitled_days"], 15)
ck_eq("特休滿3年度日數", r["result"]["periods"][3]["entitled_days"], 14)

# ── 錨點8：資遣費新制上限6個月（勞退條例§12）
r = router.run("severance", {"avg_wage": 50000, "onboard": "0940701", "leave": "1141231", "scheme": "new"})
ck("新制上限", r["result"]["parts"]["新制"]["amount"], 300000)
ck_eq("上限觸發", r["result"]["parts"]["新制"]["cap_hit"], True)

# ── 錨點9：分期 add-on 6% 十二期 ≒ 實質年利率 10.9%
r = router.run("loan.installment", {"mode": "addon", "principal": 60000, "months": 12, "fee": 3600})
ck("分期實質年利率", r["result"]["apr"], 10.9, 0.15)

# ── 錨點10：應有部分合計檢核
r = router.run("share.ratio", {"owners": [{"num": 1, "den": 3}, {"num": 1, "den": 6}, {"num": 1, "den": 2}]})
ck_eq("持分合計為1", r["result"]["is_whole"], True)

# ── 錨點11：小算盤精度
r = router.run("calc.eval", {"expr": "1000000*0.05*88/365", "precision": 2})
ck("小算盤", r["result"]["value"], 12054.79, 0.01)

# ── 錨點12：未實作工具必須拒絕出貨
for tid in ("sentence.range", "fee.court", "deadline.appeal", "inheritance.tree"):
    r = router.run(tid, {})
    ck_eq(f"{tid} 拒絕出貨", (r["ok"], bool(r.get("needs"))), (False, True))

# ── 錨點13：借款還款餘額（中間不捨入；複利/單利兩模式）
ev = [{"date": "1100101", "lend": 500000}, {"date": "1140101", "repay": 500000}]
r1 = router.run("loan.balance", {"events": ev, "apr": 5, "basis": 1, "compound": True})
r2 = router.run("loan.balance", {"events": ev, "apr": 5, "basis": 1, "compound": False})
ck("借還款單利4年利息", r2["result"]["total_interest"], 500000 * 0.05 * (1461 / 365.5), 200)
ck_eq("尚欠判讀", r1["result"]["final_balance"] > 0, True)   # 還本未還息，仍欠利息
r4 = router.run("loan.balance", {"events": [{"date": "1100101", "lend": 500000}, {"date": "1140101", "repay": 700000}], "apr": 5})
ck_eq("溢償判讀", r4["result"]["verdict"].startswith("已清償並溢償"), True)
r3 = router.run("loan.balance", {"events": ev, "apr": 5, "basis": 3})
ck_eq("basis 標示", r3["result"]["basis_label"], "實際/365")


# ── 特休離職當期全額（v0.1.2 訂正）
r = router.run("leave.annual", {"onboard": "1100101", "leave": "1150401", "monthly_wage": 45000})
ck("特休110.1.1~115.4.1 折算工資", r["result"]["unused_wage"], 94500, 0)
ck_eq("離職當期全額不打折", r["result"]["periods"][-1]["days_counted"], 15.0)
# ── 折舊平均法對照法院實例（成本7,778、5年、用3年2月 → 折舊4,105、餘3,673）
r = router.run("depreciation", {"cost": 7778, "years": 5, "used_years": 3, "used_months": 2})
ck("折舊實例累積折舊", r["result"]["accumulated_depreciation"], 4105)
ck("折舊實例現值", r["result"]["present_value"], 3673)


print("\n" + ("全部通過" if not F else f"失敗 {len(F)} 項：{F}"))
sys.exit(1 if F else 0)
