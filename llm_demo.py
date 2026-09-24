#!/usr/bin/env python3
"""twcalc × LLM 端到端示範：模型拿 schema → 自己挑工具 → 打單一入口 → 用回傳數字作答。

用法：python3 llm_demo.py "問句" [model]
預設 model＝deepseek-v4.1-flash:cloud（任何 OpenAI 相容端點皆可）。
"""
import json, os, sys, urllib.request

OLLAMA = os.environ.get("TWCALC_LLM_URL", "http://localhost:11434/v1/chat/completions")
twcalc = os.environ.get("TWCALC_URL", "http://localhost:8004")


def get(path):
    with urllib.request.urlopen(twcalc + path, timeout=20) as r:
        return json.load(r)


def post(path, body):
    req = urllib.request.Request(twcalc + path, json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return json.load(e)


def chat(model, messages, tools):
    body = {"model": model, "messages": messages, "tools": tools,
            "options": {"temperature": 0, "num_ctx": 32768}, "stream": False}
    req = urllib.request.Request(OLLAMA, json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.load(r)


def dispatch(name, args):
    if name == "twcalc_match":
        return get("/calc/match?q=" + urllib.parse.quote(args.get("q", "")))
    if name == "twcalc_run":
        return post("/calc", {"tool": args.get("tool"), "params": args.get("params") or {}})
    return {"ok": False, "error": f"未知工具 {name}"}


SYS = ("你是法官的計算助手。凡涉及金額、期間、比例、利息的數字，一律呼叫工具計算，"
       "禁止自行心算或估算。不確定該用哪支工具時先呼叫 twcalc_match。"
       "工具回 ok:false 時據實說明缺什麼，不得自行補數字。"
       "最後用中文簡答，並註明所用工具與法源。")


def main():
    q = sys.argv[1] if len(sys.argv) > 1 else "民國110年1月1日到職，115年4月1日離職，月薪4萬5，特休沒休完可以折多少錢？"
    model = sys.argv[2] if len(sys.argv) > 2 else "deepseek-v4.1-flash:cloud"
    tools = get("/calc/schema?flavor=ollama")["tools"]
    msgs = [{"role": "system", "content": SYS}, {"role": "user", "content": q}]
    print(f"[問] {q}\n[模型] {model}\n[工具] {[t['function']['name'] for t in tools]}\n")
    for turn in range(6):
        rsp = chat(model, msgs, tools)
        m = rsp["choices"][0]["message"]
        calls = m.get("tool_calls") or []
        msgs.append({"role": "assistant", "content": m.get("content") or "",
                     "tool_calls": calls} if calls else
                    {"role": "assistant", "content": m.get("content") or ""})
        if not calls:
            print("[答]\n" + (m.get("content") or "(空)"))
            return 0
        for c in calls:
            fn = c["function"]["name"]
            args = c["function"]["arguments"]
            if isinstance(args, str):
                args = json.loads(args or "{}")
            out = dispatch(fn, args)
            print(f"[呼叫 {turn+1}] {fn}({json.dumps(args, ensure_ascii=False)})")
            print(f"    → ok={out.get('ok')} " +
                  (json.dumps(out.get('result') or out.get('candidates') or out.get('error'),
                              ensure_ascii=False)[:400]))
            msgs.append({"role": "tool", "content": json.dumps(out, ensure_ascii=False)})
    print("[答] 超過回合上限")
    return 1


if __name__ == "__main__":
    import urllib.parse
    sys.exit(main())
