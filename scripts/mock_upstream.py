#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模拟 OpenAI 兼容上游渠道（mock upstream）

用途：不花一分钱联调中转站全链路——渠道验收、SSE 流式测试、
故障演练、日志排查教学。把它当成"上游水厂"接进 New API。

启动：  python mock_upstream.py --port 9000
接入：  New API 后台 → 渠道 → 添加 → 类型 OpenAI
        Base URL: http://host.docker.internal:9000
        模型列表: mock-1
"""
import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL = "mock-1"


class MockUpstream(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def _log(self, msg):
        """上游侧日志——教学用：每次被网关调用都打印一行。"""
        print(f"[mock-upstream] {time.strftime('%H:%M:%S')} {self.path} {msg}", flush=True)

    def _send_json(self, obj, status=200):
        data = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/v1/models":
            self._log("list models")
            self._send_json({"object": "list",
                             "data": [{"id": MODEL, "object": "model",
                                       "owned_by": "mock"}]})
        else:
            self._send_json({"error": {"message": f"unknown path {self.path}"}}, 404)

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self._send_json({"error": {"message": "unknown path"}}, 404)
            return
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length) or b"{}")
        except Exception:  # noqa: BLE001
            self._send_json({"error": {"message": "bad json"}}, 400)
            return
        model = body.get("model", MODEL)
        stream = body.get("stream", False)
        self._log(f"model={model} stream={stream} "
                  f"auth={self.headers.get('Authorization', '')[:16]}...")

        if not stream:
            time.sleep(0.2)  # 模拟上游处理延迟
            self._send_json({
                "id": "chatcmpl-mock", "object": "chat.completion",
                "created": int(time.time()), "model": model,
                "choices": [{"index": 0,
                             "message": {"role": "assistant",
                                         "content": "pong（来自模拟上游）"},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 8,
                          "total_tokens": 20},
            })
        else:
            # ---- SSE 流式：模拟"一个 token 一个 token 地吐" ----
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            try:
                for tok in ["好的", "，", "这是", "模拟", "上游", "的",
                            "流式", "回复", "。"]:
                    chunk = {"id": "chatcmpl-mock",
                             "object": "chat.completion.chunk",
                             "created": int(time.time()), "model": model,
                             "choices": [{"index": 0, "delta": {"content": tok},
                                          "finish_reason": None}]}
                    self.wfile.write(
                        f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
                        .encode("utf-8"))
                    self.wfile.flush()
                    time.sleep(0.12)  # 模拟 TPOT（每个 token 的间隔）
                tail = {"id": "chatcmpl-mock",
                        "object": "chat.completion.chunk",
                        "choices": [{"index": 0, "delta": {},
                                     "finish_reason": "stop"}]}
                self.wfile.write(
                    f"data: {json.dumps(tail)}\n\n".encode("utf-8"))
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
                self._log("stream done")
            except (BrokenPipeError, ConnectionAbortedError):
                self._log("stream aborted by client")

    def log_message(self, fmt, *args):  # 静音默认访问日志，只留自定义行
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=9000)
    args = ap.parse_args()
    srv = ThreadingHTTPServer(("0.0.0.0", args.port), MockUpstream)
    print(f"[mock-upstream] OpenAI 兼容模拟上游已启动: "
          f"http://localhost:{args.port}/v1  模型: {MODEL}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
