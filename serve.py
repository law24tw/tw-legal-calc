#!/usr/bin/env python3
"""台灣法律計算工具 HTTP 服務（port 8004）——LLM 單一入口。

  GET  /health
  GET  /calc/tools[?group=&status=&verbose=1]     工具目錄
  GET  /calc/describe?tool=<id>                   單支規格
  GET  /calc/match?q=<問句>                       詞彙路由（零 LLM）
  POST /calc            {"tool":"...","params":{...}}   ★ 單一入口
  GET  /calc/run?tool=<id>&params=<json>          同上（GET 版，給只會 GET 的工具鏈）
  GET  /calc/schema[?flavor=openai|ollama]        function-calling схема（給蜂群/OWUI 掛工具）
  GET  /                                          目錄頁（人看的）
"""
from __future__ import annotations
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from fastapi import FastAPI                                  # noqa: E402
from fastapi.responses import HTMLResponse, JSONResponse     # noqa: E402
from pydantic import BaseModel                               # noqa: E402
import router                                                # noqa: E402

app = FastAPI(title="台灣法律計算工具", version=router.registry()["meta"]["version"])


class CalcIn(BaseModel):
    tool: str
    params: dict | None = None


@app.get("/health")
def health():
    reg = router.registry()
    tools = reg["tools"]
    return {"ok": True, "service": "twcalc_run", "version": reg["meta"]["version"],
            "tools": len(tools), "ready": sum(1 for t in tools if t["status"] == "ready"),
            "planned": [t["id"] for t in tools if t["status"] != "ready"]}


@app.get("/calc/tools")
def tools(group: str | None = None, status: str | None = None, verbose: int = 0):
    return {"ok": True, "tools": router.list_tools(group, status, bool(verbose))}


@app.get("/calc/describe")
def describe(tool: str):
    return router.describe(tool)


@app.get("/calc/match")
def match(q: str, limit: int = 5):
    return router.match(q, limit)


@app.post("/calc")
def calc(body: CalcIn):
    out = router.run(body.tool, body.params or {})
    return JSONResponse(out, status_code=200 if out.get("ok") else 400)


@app.get("/calc/run")
def calc_get(tool: str, params: str = "{}"):
    out = router.run(tool, params)
    return JSONResponse(out, status_code=200 if out.get("ok") else 400)


_TYPE = {"number": "number", "int": "integer", "bool": "boolean", "string": "string",
         "roc_date": "string", "enum": "string", "array": "array"}


@app.get("/calc/schema")
def schema(flavor: str = "openai"):
    fns = []
    for t in router.registry()["tools"]:
        if t["status"] != "ready" or t["id"] not in router.HANDLERS:
            continue
        props, req = {}, []
        for k, spec in (t.get("params") or {}).items():
            spec = spec or {}
            p = {"type": _TYPE.get(spec.get("type"), "string"), "description": spec.get("desc", "")}
            if spec.get("type") == "roc_date":
                p["description"] = (p["description"] + "（民國 YYYMMDD，如 1150924）").strip()
            if spec.get("values"):
                p["enum"] = spec["values"]
            if spec.get("type") == "array":
                p["items"] = {"type": "object"}
            props[k] = p
            if spec.get("required"):
                req.append(k)
        fns.append({"type": "function", "function": {
            "name": "twcalc_" + t["id"].replace(".", "_"),
            "description": f"{t['name']}：{t.get('summary','')}",
            "parameters": {"type": "object", "properties": props, "required": req}}})
    single = {"type": "function", "function": {
        "name": "twcalc_run",
        "description": "司法院辦案小工具計算中心單一入口。先用 twcalc_match 問句找工具，再以 tool+params 計算。"
                       "涉及金額、期間、比例、利息的數字一律呼叫本工具，不得自行心算。",
        "parameters": {"type": "object", "properties": {
            "tool": {"type": "string", "enum": [t["id"] for t in router.registry()["tools"]],
                     "description": "工具代號"},
            "params": {"type": "object", "description": "該工具之參數物件"}},
            "required": ["tool", "params"]}}}
    matcher = {"type": "function", "function": {
        "name": "twcalc_match",
        "description": "用中文問句找出該用哪支計算工具（零 LLM 詞彙比對）。",
        "parameters": {"type": "object",
                       "properties": {"q": {"type": "string", "description": "中文問句"}},
                       "required": ["q"]}}}
    if flavor == "ollama":
        return {"tools": [single, matcher]}
    return {"single_entry": [single, matcher], "per_tool": fns}


@app.get("/", response_class=HTMLResponse)
def index():
    reg = router.registry()
    rows = []
    for t in reg["tools"]:
        rdy = t["status"] == "ready"
        rows.append(
            f"<tr class='{'r' if rdy else 'p'}'><td>{'✔' if rdy else '·'}</td>"
            f"<td><code>{t['id']}</code></td><td>{t.get('group','')}</td>"
            f"<td>{t['name']}</td><td>{t.get('summary','') or '（未實作：' + '；'.join(t.get('needs',[]))[:80] + '）'}</td></tr>")
    return f"""<!doctype html><meta charset=utf-8><title>台灣法律計算工具</title>
<style>body{{font-family:-apple-system,"PingFang TC",sans-serif;margin:2rem;max-width:1100px}}
table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{border-bottom:1px solid #ddd;padding:6px 8px;text-align:left;vertical-align:top}}
tr.p{{color:#999}}code{{background:#f4f4f4;padding:1px 4px;border-radius:3px}}h1{{font-size:20px}}
.k{{background:#f8f8f8;padding:10px;border-radius:6px;font-family:ui-monospace,monospace;font-size:13px;white-space:pre-wrap}}</style>
<h1>台灣法律計算工具 <small>v{reg['meta']['version']} · {sum(1 for t in reg['tools'] if t['status']=='ready')}/{len(reg['tools'])} 可用</small></h1>
<p>依司法院辦案小工具之公開計算式與現行法令實作。LLM 單一入口：<code>POST /calc {{"tool":..,"params":..}}</code></p>
<div class=k>curl -s localhost:8004/calc/match --get --data-urlencode "q=特休沒休完要折多少錢"
curl -s localhost:8004/calc -H 'Content-Type: application/json' \\
  -d '{{"tool":"leave.annual","params":{{"onboard":"1100101","leave":"1150401","monthly_wage":45000}}}}'</div>
<table><tr><th></th><th>id</th><th>類</th><th>名稱</th><th>做什麼</th></tr>{''.join(rows)}</table>"""
