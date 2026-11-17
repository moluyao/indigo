#!/usr/bin/env python
"""Run one eval task against the DeepSeek API and save reply / html / meta.

Usage:
  python ds_run.py --task T1 --out runs/deepseek-raw [--system sys.md] [--model deepseek-v4-pro]
"""
import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
TASKS_MD = HERE / "tasks.md"
ENV_FILE = Path(__file__).resolve().parent / ".secrets" / "deepseek.env"  # 内容：DEEPSEEK_API_KEY=你的key（不要提交到仓库）
API_URL = "https://api.deepseek.com/chat/completions"
BALANCE_URL = "https://api.deepseek.com/user/balance"
MODELS = ["deepseek-v4-pro", "deepseek-flash"]


def load_key():
    if not ENV_FILE.exists():
        sys.exit("error: key file not found")
    for line in ENV_FILE.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[7:]
        if line.startswith("DEEPSEEK_API_KEY"):
            _, _, v = line.partition("=")
            v = v.strip().strip('"').strip("'")
            if v:
                return v
    sys.exit("error: DEEPSEEK_API_KEY not found in env file")


def scrub(text, key):
    """Never let the key leak into logs / errors."""
    if key and text:
        text = text.replace(key, "***")
    return text


def parse_tasks():
    md = TASKS_MD.read_text(encoding="utf-8")
    tasks = {}
    for m in re.finditer(r"\*\*(T\d)[^*]*\*\*\s*[:：]\s*「(.+?)」", md):
        tasks[m.group(1)] = m.group(2)
    m = re.search(r"##\s*统一技术要求\s*\n(.*?)(?=\n##\s|\Z)", md, re.S)
    if not m:
        sys.exit("error: 统一技术要求 section not found in tasks.md")
    return tasks, m.group(1).strip()


def extract_html(reply):
    blocks = re.findall(r"```[ \t]*(?:html|HTML)?[^\n]*\n(.*?)```", reply, re.S)
    full = [b for b in blocks if re.search(r"<html|<!doctype", b, re.I) and re.search(r"</html>", b, re.I)]
    if full:
        return full[-1].strip() + "\n"
    # fallback: raw html document in reply
    m = list(re.finditer(r"<!DOCTYPE html.*?</html>|<html.*?</html>", reply, re.S | re.I))
    if m:
        return m[-1].group(0).strip() + "\n"
    return None


def http_json(url, key, payload=None, timeout=60):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET")
    req.add_header("Authorization", "Bearer " + key)
    req.add_header("Content-Type", "application/json")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def get_balance(key):
    try:
        return http_json(BALANCE_URL, key, timeout=30)
    except Exception as e:  # noqa
        return {"error": scrub(f"{type(e).__name__}: {e}", key)}


def cny_balance(b):
    try:
        for info in b.get("balance_infos", []):
            if info.get("currency") == "CNY":
                return float(info["total_balance"])
    except Exception:
        pass
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task", required=True, choices=["T1", "T2", "T3"])
    ap.add_argument("--system", help="optional system prompt file")
    ap.add_argument("--model", default="deepseek-v4-pro")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--max-tokens", type=int, default=32000)
    ap.add_argument("--timeout", type=int, default=1200, help="request timeout seconds")
    ap.add_argument("--local", action="store_true", help="use the local proxy in .secrets/local_llm.env instead of the official API")
    a = ap.parse_args()

    global API_URL
    if a.local:
        env = {}
        for line in (ENV_FILE.parent / "local_llm.env").read_text(encoding="utf-8-sig").splitlines():
            k, _, v = line.strip().partition("=")
            if v:
                env[k.strip()] = v.strip()
        API_URL = env["LOCAL_LLM_BASE"].rstrip("/") + "/chat/completions"
        key = env["LOCAL_LLM_KEY"]
    else:
        key = load_key()
    tasks, tech = parse_tasks()
    if a.task not in tasks:
        sys.exit(f"error: {a.task} not found in tasks.md")
    user_msg = f"{tasks[a.task]}\n\n统一技术要求：\n{tech}\n"

    messages = []
    sys_path = None
    if a.system:
        sys_path = Path(a.system).resolve()
        messages.append({"role": "system", "content": sys_path.read_text(encoding="utf-8")})
    messages.append({"role": "user", "content": user_msg})

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    payload = {"model": a.model, "messages": messages, "max_tokens": a.max_tokens, "stream": False}

    bal_before = None if a.local else get_balance(key)
    resp, err, attempts = None, None, 0
    t0 = time.time()
    for attempts in (1, 2):  # at most one retry
        try:
            resp = http_json(API_URL, key, payload, timeout=a.timeout)
            break
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")[:2000]
            except Exception:
                pass
            err = scrub(f"HTTP {e.code}: {body}", key)
            if e.code in (400, 401, 402, 403, 422):  # not retryable
                break
        except Exception as e:  # noqa
            err = scrub(f"{type(e).__name__}: {e}", key)
        print(f"[{a.task}] attempt {attempts} failed: {err}", file=sys.stderr)
        if attempts == 1:
            time.sleep(5)
    elapsed = time.time() - t0
    bal_after = None if a.local else get_balance(key)

    meta = {
        "task": a.task,
        "model": a.model,
        "system_prompt": str(sys_path) if sys_path else None,
        "max_tokens": a.max_tokens,
        "attempts": attempts,
        "elapsed_s": round(elapsed, 1),
        "started_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t0)),
        "balance_before": bal_before,
        "balance_after": bal_after,
    }
    b0, b1 = cny_balance(bal_before), cny_balance(bal_after)
    if b0 is not None and b1 is not None:
        meta["cost_cny_by_balance_delta"] = round(b0 - b1, 4)

    if resp is None:
        meta["error"] = err
        (out / f"{a.task}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        sys.exit(f"[{a.task}] failed: {err}")

    choice = (resp.get("choices") or [{}])[0]
    msg = choice.get("message") or {}
    reply = msg.get("content") or ""
    reasoning = msg.get("reasoning_content")
    meta.update({
        "response_model": resp.get("model"),
        "finish_reason": choice.get("finish_reason"),
        "usage": resp.get("usage"),
        "reply_chars": len(reply),
    })
    for k in ("cost", "price", "billing"):
        if k in resp:
            meta[k] = resp[k]

    (out / f"{a.task}.md").write_text(reply, encoding="utf-8")
    if reasoning:
        (out / f"{a.task}.reasoning.md").write_text(reasoning, encoding="utf-8")
    html = extract_html(reply)
    meta["html_extracted"] = bool(html)
    if html:
        (out / f"{a.task}.html").write_text(html, encoding="utf-8")
    (out / f"{a.task}.meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: meta.get(k) for k in ("task", "model", "elapsed_s", "finish_reason", "usage",
                                              "html_extracted", "cost_cny_by_balance_delta")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
