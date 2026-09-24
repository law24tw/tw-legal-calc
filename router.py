#!/usr/bin/env python3
"""台灣法律計算工具 — 路由器（LLM 單一入口）。

設計：LLM 不必記 20 支工具的參數，只要打一個入口。
  router.list_tools()            → 目錄（含參數規格）
  router.match("特休怎麼算")      → 候選工具（純詞彙比對，零 LLM、零網路）
  router.describe("leave.annual")→ 單支規格
  router.run("leave.annual", {…})→ 統一信封 {ok, result, basis, formula}

鐵則：registry.yaml 裡 status != ready 的工具，一律回 ok:false + needs，
      絕不臆測數字（「取不到不准出貨」）。
CLI：
  python3 router.py list
  python3 router.py describe leave.annual
  python3 router.py match 特休
  python3 router.py run time.elapsed '{"start":"1100101","end":"1150401"}'
"""
from __future__ import annotations
import json, os, re, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import yaml                                          # noqa: E402
from calc.dates import CalcError                     # noqa: E402
from calc import basic, period, money, hoffmann, labor, land, loan, address, fees, sentence  # noqa: E402

_REG = None
_MTIME = None


def registry(force=False):
    """熱讀 registry.yaml（改 YAML 免重啟）。"""
    global _REG, _MTIME
    p = os.path.join(HERE, "registry.yaml")
    mt = os.path.getmtime(p)
    if force or _REG is None or mt != _MTIME:
        with open(p, encoding="utf-8") as f:
            _REG = yaml.safe_load(f)
        _MTIME = mt
    return _REG


# tool_id → 實作函式
HANDLERS = {
    "calc.eval":            basic.evaluate,
    "time.elapsed":         period.elapsed,
    "interest.penalty":     money.interest_penalty,
    "penalty.interest":     money.penalty_items,
    "depreciation":         money.depreciation,
    "rent.unjust":          money.unjust_rent,
    "hoffmann.lump":        hoffmann.lump_sum,
    "hoffmann.pv_periodic": hoffmann.pv_periodic,
    "severance":            labor.severance,
    "leave.annual":         labor.annual_leave,
    "share.ratio":          land.share_ratio,
    "land.partition":       land.partition,
    "land.keep_share":      land.keep_share,
    "land.merge_share":     land.merge_share,
    "loan.installment":     loan.installment,
    "loan.balance":         loan.balance,
    "address.court":        address.resolve,
    "fee.court":            fees.court_fee,
    "sentence.range":       sentence.sentence_range,
}

def keywords():
    """詞彙路由表：住 registry.yaml 的 routing: 區（可校訂、熱讀）。"""
    return registry().get("routing", {})


def _tool(tid):
    for t in registry()["tools"]:
        if t["id"] == tid:
            return t
    return None


def list_tools(group=None, status=None, verbose=False):
    out = []
    for t in registry()["tools"]:
        if group and t.get("group") != group:
            continue
        if status and t.get("status") != status:
            continue
        row = {"id": t["id"], "name": t["name"], "group": t.get("group"),
               "status": t.get("status"), "summary": t.get("summary", "")}
        if verbose:
            row["params"] = t.get("params") or t.get("inputs")
            row["basis"] = t.get("basis")
        out.append(row)
    return out


def describe(tool_id):
    t = _tool(tool_id)
    if not t:
        return {"ok": False, "error": f"無此工具：{tool_id}",
                "hint": "先呼叫 list 取得目錄", "available": [x["id"] for x in registry()["tools"]]}
    d = dict(t)
    d["ok"] = True
    d["callable"] = tool_id in HANDLERS and t.get("status") == "ready"
    return d


def match(q, limit=5):
    """詞彙路由：問句 → 候選工具。純比對，零 LLM。"""
    q = str(q or "")
    qn = re.sub(r"\s+", "", q)
    scores = {}
    for tid, kws in keywords().items():
        s = sum(len(k) for k in kws if k in qn)
        if s:
            scores[tid] = s
    for t in registry()["tools"]:
        if t["name"] and t["name"] in qn:
            scores[t["id"]] = scores.get(t["id"], 0) + len(t["name"]) * 3
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])[:limit]
    cands = []
    for tid, s in ranked:
        t = _tool(tid) or {}
        cands.append({"id": tid, "name": t.get("name"), "status": t.get("status"),
                      "score": s, "summary": t.get("summary", ""),
                      "params": t.get("params") or t.get("inputs")})
    return {"query": q, "candidates": cands,
            "note": "詞彙比對結果；無命中時請呼叫 list 自行挑選，勿自行心算"}


def run(tool, params=None):
    """單一入口。回傳統一信封。"""
    params = params or {}
    if isinstance(params, str):
        try:
            params = json.loads(params)
        except json.JSONDecodeError as e:
            return {"ok": False, "tool": tool, "error": f"params 不是合法 JSON：{e}"}
    t = _tool(tool)
    if not t:
        m = match(tool)
        return {"ok": False, "tool": tool, "error": f"無此工具：{tool}",
                "did_you_mean": [c["id"] for c in m["candidates"]],
                "available": [x["id"] for x in registry()["tools"]]}
    env = {"ok": False, "tool": tool, "name": t["name"], "group": t.get("group"),
           "status": t.get("status"), "version": registry()["meta"]["version"]}
    if t.get("status") != "ready" or tool not in HANDLERS:
        env.update({"error": "本工具尚未實作，依鐵則不臆測數字",
                    "needs": t.get("needs", []), "inputs_spec": t.get("inputs"),
                    "basis": t.get("basis"),
                    "advice": "請先補齊 needs 所列資料檔，或改用 calc.eval 自行列式並敘明計算過程"})
        if t.get("risk"):
            env["risk"] = t["risk"]
        return env
    # 表格供料（registry 的 tables 區）
    if t.get("table_ref"):
        ref = t["table_ref"].split(".")
        tbl = registry()
        for k in ref:
            tbl = tbl.get(k, {})
        params = dict(params, table=tbl)
    try:
        res = HANDLERS[tool](**params)
    except CalcError as e:
        return {**env, "error": f"輸入有誤：{e}", "params_spec": t.get("params")}
    except TypeError as e:
        return {**env, "error": f"參數不合：{e}", "params_spec": t.get("params")}
    except Exception as e:                                   # noqa: BLE001
        return {**env, "error": f"{type(e).__name__}: {e}", "params_spec": t.get("params")}
    env.update({"ok": True, "params": {k: v for k, v in params.items() if k != "table"},
                "result": res, "basis": t.get("basis")})
    if t.get("caution"):
        env["caution"] = t["caution"]
    return env


def _main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 1
    cmd = argv[1]
    if cmd == "list":
        rows = list_tools(status=argv[2] if len(argv) > 2 else None)
        w = max(len(r["id"]) for r in rows)
        for r in rows:
            flag = "✔" if r["status"] == "ready" else "·"
            print(f"{flag} {r['id']:<{w}}  {r['group'] or '':<4} {r['name']}")
        print(f"\n共 {len(rows)} 支，ready {sum(1 for r in rows if r['status']=='ready')} 支")
    elif cmd == "describe":
        print(json.dumps(describe(argv[2]), ensure_ascii=False, indent=2))
    elif cmd == "match":
        print(json.dumps(match(" ".join(argv[2:])), ensure_ascii=False, indent=2))
    elif cmd == "run":
        print(json.dumps(run(argv[2], argv[3] if len(argv) > 3 else "{}"),
                         ensure_ascii=False, indent=2))
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv))
