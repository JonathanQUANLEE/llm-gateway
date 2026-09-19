#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网关冒烟测试 + 故障演练

对网关做 5 项测试，前 3 项故意制造故障，观察每种错误在网关上的真实表现
（这就是 JD 里"排障"的日常：先复现，看状态码，再归因）。

用法：
  set API_KEY=sk-你在后台生成的令牌      (Windows)
  python smoke_test.py [--base http://localhost:3000] [--model deepseek-chat]
"""
import argparse
import json
import sys

import requests

PASS, FAIL, INFO = "PASS", "FAIL", "INFO"


def check(idx, title, ok, detail=""):
    tag = PASS if ok is True else (FAIL if ok is False else INFO)
    print(f"[{idx}] {tag}  {title}")
    if detail:
        print(f"      {detail}")
    print()
    return tag == PASS


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:3000")
    ap.add_argument("--key", default=None, help="网关令牌，默认取环境变量 API_KEY")
    ap.add_argument("--model", default="deepseek-chat")
    args = ap.parse_args()

    key = args.key or __import__("os").environ.get("API_KEY", "")
    base = args.base.rstrip("/")
    print(f"目标网关: {base}   模型: {args.model}\n" + "=" * 60 + "\n")

    body = {"model": args.model, "messages": [{"role": "user", "content": "hi"}]}
    n_pass = 0

    # 1) 不带鉴权头 -> 预期 401
    try:
        r = requests.post(f"{base}/v1/chat/completions", json=body, timeout=30)
        n_pass += check(1, f"无鉴权头（预期 401）: 实际 {r.status_code}", r.status_code == 401,
                        r.text[:120])
    except Exception as e:  # noqa: BLE001
        check(1, "无鉴权头", False, f"连接失败: {e}")

    # 2) 错误 key -> 预期 401
    try:
        r = requests.post(f"{base}/v1/chat/completions",
                          headers={"Authorization": "Bearer sk-invalid-key-000"},
                          json=body, timeout=30)
        n_pass += check(2, f"错误 key（预期 401）: 实际 {r.status_code}", r.status_code == 401,
                        r.text[:120])
    except Exception as e:  # noqa: BLE001
        check(2, "错误 key", False, f"连接失败: {e}")

    # 3) 不存在的模型 -> 观察返回什么并记录（不同网关表现不同：404 / 503 等）
    try:
        r = requests.post(f"{base}/v1/chat/completions",
                          headers={"Authorization": f"Bearer {key}"},
                          json={"model": "not-exist-model-000",
                                "messages": [{"role": "user", "content": "hi"}]},
                          timeout=30)
        n_pass += check(3, f"不存在模型（预期非 200）: 实际 {r.status_code}",
                        r.status_code != 200, r.text[:160])
    except Exception as e:  # noqa: BLE001
        check(3, "不存在模型", False, f"连接失败: {e}")

    # 4) 正常调用 -> 预期 200 + usage
    try:
        r = requests.post(f"{base}/v1/chat/completions",
                         headers={"Authorization": f"Bearer {key}"},
                         json={"model": args.model, "max_tokens": 50,
                               "messages": [{"role": "user", "content": "用一句话介绍你自己"}]},
                         timeout=60)
        ok = r.status_code == 200
        usage = ""
        if ok:
            j = r.json()
            usage = f"回复: {j['choices'][0]['message']['content'][:50]}... | usage: {j.get('usage')}"
        n_pass += check(4, f"正常调用（预期 200）: 实际 {r.status_code}", ok, usage or r.text[:160])
    except Exception as e:  # noqa: BLE001
        check(4, "正常调用", False, f"连接失败: {e}")

    # 5) 流式调用 -> 预期 data: 分块 + [DONE] 收尾
    try:
        r = requests.post(f"{base}/v1/chat/completions",
                         headers={"Authorization": f"Bearer {key}"},
                         json={"model": args.model, "stream": True, "max_tokens": 60,
                               "messages": [{"role": "user", "content": "从1数到5"}]},
                         stream=True, timeout=60)
        chunks, done = 0, False
        first = ""
        for raw in r.iter_lines():
            line = raw.decode("utf-8", errors="ignore")
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                done = True
                break
            chunks += 1
            if not first and '"content"' in data:
                try:
                    first = json.loads(data)["choices"][0]["delta"].get("content", "")
                except Exception:  # noqa: BLE001
                    pass
        n_pass += check(5, f"流式调用: chunks={chunks}, 收尾[DONE]={done}",
                        r.status_code == 200 and chunks > 0 and done,
                        f"首个内容片段: {first[:40]!r}")
    except Exception as e:  # noqa: BLE001
        check(5, "流式调用", False, f"连接失败: {e}")

    print("=" * 60)
    print(f"结果: {n_pass}/5 通过")
    print("提示: 第 1-3 项是故意制造的故障，用来观察网关每种错误的真实表现；")
    print("      第 4-5 项通过 = 网关全链路正常。")
    return 0 if n_pass == 5 else 1


if __name__ == "__main__":
    sys.exit(main())
