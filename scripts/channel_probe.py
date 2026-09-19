#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
渠道测活 / 测速脚本（渠道验收用）

对每个上游渠道做两项探测：
  1. 非流式请求：连通性、状态码、总延迟、usage 用量
  2. 流式请求：TTFT（首 token 延迟）、流式总耗时、chunk 数

用法：
  python channel_probe.py --config channels.json
  python channel_probe.py --url https://上游地址 --key sk-xxx --model gpt-4o-mini

channels.json 格式：
{
  "channels": [
    {"name": "渠道A", "base_url": "https://xxx", "api_key": "sk-xxx", "model": "deepseek-chat"},
    {"name": "渠道B", "base_url": "https://yyy", "api_key": "sk-yyy", "model": "gpt-4o-mini"}
  ]
}
"""
import argparse
import json
import sys
import time

import requests

TIMEOUT = 30


def probe_channel(name, base_url, api_key, model):
    """探测单个渠道，返回结果 dict。"""
    r = {"渠道": name, "模型": model}
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "messages": [{"role": "user", "content": "ping"}], "max_tokens": 64}

    # ---------- 1) 非流式：连通性 + 总延迟 + usage ----------
    t0 = time.time()
    try:
        resp = requests.post(f"{base_url}/v1/chat/completions",
                             headers=headers, json=payload, timeout=TIMEOUT)
        r["状态码"] = resp.status_code
        r["总延迟"] = f"{time.time() - t0:.2f}s"
        if resp.status_code == 200:
            usage = resp.json().get("usage", {})
            r["tokens"] = usage.get("total_tokens", "-")
        else:
            try:
                r["错误"] = resp.json().get("error", {}).get("message", "")[:60]
            except Exception:
                r["错误"] = resp.text[:60]
            return r
    except requests.exceptions.Timeout:
        r["状态码"] = "TIMEOUT"
        return r
    except requests.exceptions.ConnectionError:
        r["状态码"] = "CONN_ERR"
        return r
    except Exception as e:  # noqa: BLE001
        r["状态码"] = f"ERR:{type(e).__name__}"
        return r

    # ---------- 2) 流式：TTFT / 总耗时 / chunk 数 ----------
    payload["stream"] = True
    ttft = None
    n_chunks = 0
    t0 = time.time()
    try:
        with requests.post(f"{base_url}/v1/chat/completions",
                           headers=headers, json=payload,
                           stream=True, timeout=TIMEOUT * 2) as resp:
            if resp.status_code != 200:
                r["TTFT"] = f"流式HTTP{resp.status_code}"
                return r
            for raw in resp.iter_lines():
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="ignore")
                if not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                n_chunks += 1
                if ttft is None:
                    ttft = time.time() - t0
        total = time.time() - t0
        r["TTFT"] = f"{ttft:.2f}s" if ttft is not None else "无输出"
        r["流式耗时"] = f"{total:.2f}s"
        r["chunks"] = n_chunks
        # 完整性检查：正常流式必须以 [DONE] 收尾且至少有 1 个 chunk
        r["流式完整"] = "OK" if (n_chunks > 0) else "FAIL"
    except Exception as e:  # noqa: BLE001
        r["TTFT"] = f"FAIL:{type(e).__name__}"
    return r


def print_table(rows):
    cols = ["渠道", "模型", "状态码", "总延迟", "TTFT", "tokens", "chunks", "流式完整", "错误"]
    widths = {c: max(len(str(c)), *(len(str(row.get(c, ""))) for row in rows)) for c in cols}
    head = " | ".join(str(c).ljust(widths[c]) for c in cols)
    print(head)
    print("-" * len(head))
    for row in rows:
        print(" | ".join(str(row.get(c, "")).ljust(widths[c]) for c in cols))


def main():
    ap = argparse.ArgumentParser(description="LLM 上游渠道测活/测速")
    ap.add_argument("--config", help="channels.json 路径")
    ap.add_argument("--url", help="单个渠道 base_url")
    ap.add_argument("--key", help="API key")
    ap.add_argument("--model", default="gpt-4o-mini")
    args = ap.parse_args()

    channels = []
    if args.config:
        with open(args.config, encoding="utf-8") as f:
            channels = json.load(f)["channels"]
    elif args.url and args.key:
        channels = [{"name": "CLI", "base_url": args.url,
                     "api_key": args.key, "model": args.model}]
    else:
        ap.error("需要 --config 或 --url + --key")

    rows = []
    for ch in channels:
        print(f"探测中: {ch['name']} ({ch['model']}) ...", flush=True)
        rows.append(probe_channel(ch["name"], ch["base_url"],
                                  ch["api_key"], ch.get("model", args.model)))
    print()
    print_table(rows)
    bad = [r for r in rows if r.get("状态码") != 200 or r.get("流式完整") == "FAIL"]
    print(f"\n结论: {len(rows) - len(bad)}/{len(rows)} 个渠道健康"
          + ("，异常渠道需要处理！" if bad else ""))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
