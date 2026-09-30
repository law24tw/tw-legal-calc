"""繼承系統表與應繼分（民法§1138–§1141、§1144、§1145、§1176、§1223；決定論、零 LLM）。
輸入：配偶與各繼承人之關係／狀態（在世、繼承開始前死亡、拋棄、喪失繼承權）；輸出：適用順序、每人應繼分（分數）、特留分、系統表文字、旗標。
規則（逐條對照 data/raw/inheritance.yaml 原文與 LFinder §1145／§1223）：
  §1138 順序：配偶外，一、直系血親卑親屬；二、父母；三、兄弟姊妹；四、祖父母。
  §1139 第一順序以親等近者為先。§1141 同一順序數人按人數平均。
  §1140 第一順序繼承人於繼承開始前死亡或喪失繼承權者，由其直系血親卑親屬代位繼承「其應繼分」（按股）。
  §1144 配偶：與第一順序同為繼承→與他繼承人平均；與第二、三順序→二分之一；與第四順序→三分之二；無各順序繼承人→全部。
  §1176 拋棄：Ⅰ第一順序拋棄者其應繼分歸其他同為繼承之人；Ⅱ第二至四順序拋棄者歸同一順序其他人；Ⅲ與配偶同為繼承之同一順序均拋棄而無後順序者歸配偶；
        Ⅳ配偶拋棄歸與其同為繼承之人；Ⅴ第一順序親等近者均拋棄→次親等直系血親卑親屬繼承；Ⅵ先順序均拋棄→次順序繼承。
  拋棄者之直系血親卑親屬不代位（§1140 事由僅「死亡或喪失繼承權」）。
  §1223 特留分：直系血親卑親屬、父母、配偶＝應繼分二分之一；兄弟姊妹、祖父母＝三分之一（§1224 由應繼財產除去債務額算定，本工具只出比例）。
不做的事（誠實邊界）：遺囑指定應繼分與遺贈扣減（§1187、§1225）、收養關係之認定（以輸入為準）、胎兒（§1166）、同時死亡推定（§11）、
  大陸地區人民繼承之限額（兩岸條例§67）、限定繼承下之清算——皆回旗標、不代判。
"""
from __future__ import annotations
from fractions import Fraction
from .dates import CalcError

ORDER1 = ("child", "grandchild", "great_grandchild")   # 直系血親卑親屬：親等 1/2/3
DEGREE = {"child": 1, "grandchild": 2, "great_grandchild": 3}
ORDERS = [("第一順序 直系血親卑親屬", ORDER1), ("第二順序 父母", ("parent",)), ("第三順序 兄弟姊妹", ("sibling",)), ("第四順序 祖父母", ("grandparent",))]
STATUS = ("alive", "dead_before", "renounced", "disqualified")
RESERVE = {1: Fraction(1, 2), 2: Fraction(1, 2), 3: Fraction(1, 3), 4: Fraction(1, 3), "spouse": Fraction(1, 2)}
BASIS = ["民法§1138", "民法§1139", "民法§1140", "民法§1141", "民法§1144", "民法§1145", "民法§1176", "民法§1223（現行；另有未生效修正版，生效後比例須重核）", "民法§1224"]

def _f(x: Fraction) -> str:
    return "0" if x == 0 else (f"{x.numerator}/{x.denominator}" if x.denominator != 1 else str(x.numerator))

def _norm(h: dict, i: int) -> dict:
    rel = (h.get("relation") or "").strip()
    if rel not in DEGREE and rel not in ("parent", "sibling", "grandparent"):
        raise CalcError(f"繼承人 #{i+1} relation 須為 child／grandchild／great_grandchild／parent／sibling／grandparent，收到 {rel!r}")
    st = (h.get("status") or "alive").strip()
    if st not in STATUS:
        raise CalcError(f"繼承人 #{i+1} status 須為 alive／dead_before／renounced／disqualified，收到 {st!r}")
    return {"name": h.get("name") or f"{rel}{i+1}", "relation": rel, "status": st, "via": (h.get("via") or "").strip(), "note": h.get("note") or ""}

def _descendant_shares(people: list[dict], parent_name: str | None, degree: int, flags: list, tree: list, indent: str) -> tuple[list[tuple[dict, Fraction]], int]:
    """回傳 [(人, 佔本層份額之權重分數)]：本層＝parent_name 之子（或 degree 層）；死亡／喪失者由其卑親屬代位（按股）；拋棄者不計且不代位。"""
    layer = [p for p in people if DEGREE.get(p["relation"]) == degree and ((p["via"] or "") == (parent_name or "") if degree > 1 else True)]
    stems: list[tuple[dict, Fraction, list]] = []   # (人, 權重, 代位子表)
    for p in layer:
        if p["status"] == "alive":
            stems.append((p, Fraction(1), [])); tree.append(f"{indent}{p['name']}（{p['relation']}·在世）")
        elif p["status"] in ("dead_before", "disqualified"):
            why = "繼承開始前死亡" if p["status"] == "dead_before" else "喪失繼承權（§1145）"
            sub, n_sub = _descendant_shares(people, p["name"], degree + 1, flags, tree, indent + "  ")
            if sub:
                stems.append((p, Fraction(1), sub)); tree.insert(len(tree) - n_sub, f"{indent}{p['name']}（{p['relation']}·{why}）→ 由其直系血親卑親屬代位（§1140）")
            else:
                tree.append(f"{indent}{p['name']}（{p['relation']}·{why}·無可代位之卑親屬）")
        elif p["status"] == "renounced":
            tree.append(f"{indent}{p['name']}（{p['relation']}·拋棄繼承）")
            if any(q["via"] == p["name"] for q in people):
                flags.append(f"{p['name']} 拋棄繼承，其直系血親卑親屬不代位（§1140 事由僅死亡或喪失繼承權；§1176Ⅰ 歸其他同為繼承之人）")
    out: list[tuple[dict, Fraction]] = []
    n_heads = len(stems)
    for p, w, sub in stems:
        if sub:
            tot = sum(x for _, x in sub)
            for q, x in sub: out.append((q, w * x / tot))
        else:
            out.append((p, w))
    n_lines = sum(1 for _ in layer)
    return out, n_lines

def tree(decedent: str = "被繼承人", spouse: dict | None = None, heirs: list | None = None, **_) -> dict:
    heirs = [_norm(h, i) for i, h in enumerate(heirs or [])]
    flags: list[str] = []; lines: list[str] = [f"{decedent}"]
    sp = None
    if spouse:
        sst = (spouse.get("status") or "alive").strip()
        if sst not in STATUS: raise CalcError(f"spouse.status 須為 alive／dead_before／renounced／disqualified，收到 {sst!r}")
        sp = {"name": spouse.get("name") or "配偶", "status": sst}
        lines.append(f"  配偶 {sp['name']}（{ {'alive':'在世','dead_before':'先死亡','renounced':'拋棄繼承','disqualified':'喪失繼承權'}[sst] }）")
    spouse_in = bool(sp and sp["status"] == "alive")
    if sp and sp["status"] == "renounced": flags.append("配偶拋棄繼承，其應繼分歸與其同為繼承之人（§1176Ⅳ）")

    # ── 依順序找出實際繼承之人 ──
    order_used = None; group: list[tuple[dict, Fraction]] = []
    for idx, (label, rels) in enumerate(ORDERS, 1):
        members = [h for h in heirs if h["relation"] in rels]
        if not members: continue
        if idx == 1:
            lines.append("  第一順序 直系血親卑親屬：")
            # §1139 親等近者為先；§1176Ⅴ 近親等均拋棄→次親等
            for deg in (1, 2, 3):
                present = [h for h in heirs if DEGREE.get(h["relation"]) == deg]
                if not present: continue
                if all(h["status"] == "renounced" for h in present):
                    flags.append(f"第一順序親等 {deg} 者均拋棄繼承，由次親等之直系血親卑親屬繼承（§1176Ⅴ）")
                    for h in present: lines.append(f"    {h['name']}（{h['relation']}·拋棄繼承）")
                    continue
                if deg == 1:
                    shares, _ = _descendant_shares(heirs, None, 1, flags, lines, "    ")
                else:
                    # 次親等承接：該層所有非拋棄者按人數平均（不再按股）
                    shares = []
                    for h in present:
                        if h["status"] == "alive": shares.append((h, Fraction(1))); lines.append(f"    {h['name']}（{h['relation']}·在世）")
                        elif h["status"] in ("dead_before", "disqualified"):
                            sub, _ = _descendant_shares(heirs, h["name"], deg + 1, flags, lines, "      ")
                            if sub:
                                tot = sum(x for _, x in sub); lines.insert(len(lines) - len(sub), f"    {h['name']}（{h['relation']}·由其卑親屬代位 §1140）")
                                shares += [(q, x / tot) for q, x in sub]
                        else: lines.append(f"    {h['name']}（{h['relation']}·拋棄繼承）")
                if shares: order_used, group = 1, shares; break
            if group: break
            flags.append("第一順序無人繼承（均拋棄／死亡且無可代位者），依§1176Ⅵ由次順序繼承")
        else:
            lines.append(f"  {label}：")
            alive = []
            for h in members:
                tag = {"alive": "在世", "dead_before": "先死亡（本順序無代位）", "renounced": "拋棄繼承", "disqualified": "喪失繼承權（本順序無代位）"}[h["status"]]
                lines.append(f"    {h['name']}（{tag}）")
                if h["status"] == "alive": alive.append(h)
            if alive:
                order_used, group = idx, [(h, Fraction(1)) for h in alive]; break
            flags.append(f"{label}均拋棄或不存在，依§1176Ⅵ由次順序繼承")

    # ── 應繼分 ──
    result: dict = {"decedent": decedent, "order_used": order_used, "heirs": [], "spouse": None, "flags": flags, "tree": "\n".join(lines), "basis": BASIS}
    if not group and not spouse_in:
        if sp and sp["status"] == "renounced" and not group:
            flags.append("配偶與各順序繼承人均拋棄，準用無人承認繼承之規定（§1176Ⅵ、§1177 以下）")
        else:
            flags.append("查無繼承人；準用關於無人承認繼承之規定（§1176Ⅵ、§1177 以下）")
        result["ok_note"] = "無人承認繼承"; return result
    total_w = sum(x for _, x in group)
    if not group:                       # 只有配偶
        spouse_share = Fraction(1); flags.append("無§1138 各順序繼承人，配偶應繼分為遺產全部（§1144④）")
    elif not spouse_in:
        spouse_share = Fraction(0)
    elif order_used == 1:
        spouse_share = Fraction(1, _heads(group) + 1)   # §1144① 與第一順序平均：以股數計
    elif order_used in (2, 3):
        spouse_share = Fraction(1, 2)
    else:
        spouse_share = Fraction(2, 3)
    if group:
        rest = Fraction(1) - spouse_share
        if order_used == 1:
            # 配偶與第一順序「平均」：以股數計（代位者合佔一股）
            per_head = rest / _heads(group)
            # group 內權重已是按股分配（每股權重 1 分給代位者），故 share = 權重 × per_head
            for p, x in group:
                sh = x * per_head
                result["heirs"].append(_heir_row(p, sh, order_used))
        else:
            for p, x in group:
                result["heirs"].append(_heir_row(p, rest * x / total_w, order_used))
    if spouse_in:
        result["spouse"] = {"name": sp["name"], "share": _f(spouse_share), "share_float": round(float(spouse_share), 6),
                            "compulsory_portion": _f(spouse_share * RESERVE["spouse"]), "basis": "民法§1144" + {1: "①", 2: "②", 3: "②", 4: "③", None: "④"}[order_used]}
    s = sum(Fraction(h["share"]) for h in result["heirs"]) + (spouse_share if spouse_in else 0)
    if s != 1: flags.append(f"⚠ 應繼分合計 {_f(s)} ≠ 1，請檢查輸入")
    result["sum_check"] = _f(s)
    return result

def _heads(group) -> int:
    """股數：在世者各一股；代位者以其被代位人為一股（權重合計 1）。group 權重之和即股數。"""
    return int(sum(x for _, x in group))

def _heir_row(p: dict, share: Fraction, order_used: int) -> dict:
    return {"name": p["name"], "relation": p["relation"], "via": p["via"] or None, "share": _f(share), "share_float": round(float(share), 6),
            "compulsory_portion": _f(share * RESERVE[order_used]), "order": order_used}
