#!/usr/bin/env python3
"""MCP stdio server — 讓 GitHub Copilot / Claude Desktop / Cursor 等直接掛上這些計算工具。

零額外相依（只用標準函式庫＋pyyaml），不連外、不呼叫任何模型。
設定範例見 README「接上 Copilot」一節。
"""
from __future__ import annotations
import json, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import router  # noqa: E402

PROTOCOL = "2025-06-18"

TOOLS = [
    {
        "name": "legal_calc",
        "title": "台灣法律計算（單一入口）",
        "description": (
            "台灣法官辦案常用計算的單一入口：期間、利息、違約金、折舊、霍夫曼折現、"
            "資遣費、特休、土地應有部分、相當租金不當得利、分期利率、借還款餘額。"
            "凡涉及金額、期間、比例、利息的數字一律呼叫本工具，不得自行心算。"
            "不確定用哪支工具時先呼叫 legal_calc_match。日期一律民國 YYYMMDD（如 1150924）。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "tool": {"type": "string", "description": "工具代號，見 legal_calc_list"},
                "params": {"type": "object", "description": "該工具之參數物件"},
            },
            "required": ["tool", "params"],
        },
    },
    {
        "name": "legal_calc_match",
        "title": "問句找工具",
        "description": "用中文問句找出該用哪支計算工具（純詞彙比對，零 LLM、零網路）。",
        "inputSchema": {
            "type": "object",
            "properties": {"q": {"type": "string", "description": "中文問句"}},
            "required": ["q"],
        },
    },
    {
        "name": "legal_calc_list",
        "title": "工具目錄",
        "description": "列出所有計算工具與其狀態（ready／待補料）。",
        "inputSchema": {"type": "object", "properties": {
            "group": {"type": "string", "description": "可選：通用／民事／刑事／其他／自建"}}},
    },
    {
        "name": "legal_calc_describe",
        "title": "工具規格",
        "description": "取得單一工具的完整參數規格與法源。",
        "inputSchema": {"type": "object", "properties": {
            "tool": {"type": "string"}}, "required": ["tool"]},
    },
]


def call(name, args):
    if name == "legal_calc":
        return router.run(args.get("tool", ""), args.get("params") or {})
    if name == "legal_calc_match":
        return router.match(args.get("q", ""))
    if name == "legal_calc_list":
        return {"ok": True, "tools": router.list_tools(args.get("group"))}
    if name == "legal_calc_describe":
        return router.describe(args.get("tool", ""))
    raise ValueError(f"unknown tool: {name}")


def send(obj):
    sys.stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def main():
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
        try:
            if method == "initialize":
                res = {"protocolVersion": PROTOCOL, "capabilities": {"tools": {}},
                       "serverInfo": {"name": "tw-legal-calc",
                                      "version": router.registry()["meta"]["version"]}}
            elif method in ("notifications/initialized", "notifications/cancelled"):
                continue
            elif method == "ping":
                res = {}
            elif method == "tools/list":
                res = {"tools": TOOLS}
            elif method == "tools/call":
                out = call(params.get("name", ""), params.get("arguments") or {})
                res = {"content": [{"type": "text",
                                    "text": json.dumps(out, ensure_ascii=False, indent=2)}],
                       "isError": not out.get("ok", True)}
            else:
                if mid is not None:
                    send({"jsonrpc": "2.0", "id": mid,
                          "error": {"code": -32601, "message": f"method not found: {method}"}})
                continue
            if mid is not None:
                send({"jsonrpc": "2.0", "id": mid, "result": res})
        except Exception as e:                                    # noqa: BLE001
            if mid is not None:
                send({"jsonrpc": "2.0", "id": mid,
                      "error": {"code": -32603, "message": f"{type(e).__name__}: {e}"}})


if __name__ == "__main__":
    main()
