"""A local stand-in for AI model APIs, for tests and for recording CLI output without an account: OpenAI-compatible
(Chat Completions), Anthropic-compatible (Messages) and Gemini (generateContent), all streaming.

It is scripted by the last user message:
  CALL <tool> <json args>   one tool call per model turn, in order, then a text answer quoting the last result
  MULTI                     all the CALL lines in one turn instead
  LOOP                      call list_tabs forever (for step caps)
  SLOW                      stream the answer slowly (for Stop)
  RATE                      answer 429 with Retry-After: 7
  NANWAIT                   answer 429 with Retry-After: nan
  HUGE                      report the largest token counts there are
With no directive it streams "Hello from the fake model." in pieces. A tool is matched by name or by suffix
("still_list_tabs", "mcp_still_list_tabs" and "mcp__still__list_tabs" all match list_tabs).

Run alone: python fakemodels.py [port] [key]. GET /_requests lists what it received (keys never included); GET /page is
a page with one button.
"""
import json
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODELS = ["fake-small", "fake-large", "plain-model"]  # plain-model ignores tools, like an endpoint without tool calling


class Fake:
    def __init__(self, key="test-key", port=0):
        self.key, self.requests, self.last = key, [], {}
        self.server = ThreadingHTTPServer(("127.0.0.1", port), self.handler())
        self.port = self.server.server_address[1]
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    @property
    def url(self):
        return "http://127.0.0.1:%d" % self.port

    def stop(self):
        self.server.shutdown()

    def handler(self):
        fake = self

        class H(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def json(self, code, body, headers=None):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.end_headers()
                self.wfile.write(data)

            def sse(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "close")
                self.end_headers()
                self.close_connection = True

            def event(self, data, name=None):
                self.wfile.write(((("event: %s\n" % name) if name else "") + "data: " + json.dumps(data) + "\n\n").encode())
                self.wfile.flush()

            def key_ok(self):
                got = self.headers.get("x-api-key") or self.headers.get("x-goog-api-key") or (self.headers.get("Authorization") or "").removeprefix("Bearer ")
                return got == fake.key or fake.key == "", bool(got)

            def do_GET(self):
                if self.path == "/_requests":
                    return self.json(200, fake.requests)
                if self.path.startswith("/page"):  # a page with a button, for approval cards
                    data = b"<!doctype html><title>Fake shop</title><button onclick=\"document.title='Pressed'\">Press me</button><button>Do nothing</button>"
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    return self.wfile.write(data)
                ok, _ = self.key_ok()
                if not ok:
                    return self.json(401, {"error": {"type": "authentication_error", "message": "Invalid API key"}})
                if self.path.rstrip("/").endswith("/models"):
                    return self.json(200, {"object": "list", "data": [{"id": m, "object": "model", "type": "model", "display_name": m} for m in MODELS]})
                self.json(404, {"error": {"message": "not found"}})

            def do_POST(self):
                body = self.body = fake.last = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                ok, sent = self.key_ok()
                kind = "anthropic" if self.path.endswith("/messages") else "openai" if self.path.endswith("/chat/completions") else "gemini" if ":" in self.path else "?"
                model = body.get("model") or self.path.partition("models/")[2].partition(":")[0]
                text, done = last_user(kind, body)
                tools = tool_names(kind, body)
                fake.requests.append({"path": self.path.split("?")[0], "kind": kind, "model": model, "keySent": sent, "keyOk": ok, "stream": body.get("stream", ":stream" in self.path),
                    "tools": tools, "messages": len(body.get("messages") or body.get("contents") or []), "chars": len(json.dumps(body.get("messages") or body.get("contents") or [])),
                    "system": len(json.dumps(body.get("system") or body.get("systemInstruction") or "")),
                    "effort": body.get("reasoning_effort"), "thinking": body.get("thinking"), "user": text[-300:], "at": time.time()})
                if not ok:
                    return self.json(401, {"error": {"type": "authentication_error", "message": "Invalid API key"}})
                if kind == "?":
                    return self.json(404, {"error": {"message": "not found"}})
                if model not in MODELS and not model.startswith("gemini"):
                    return self.json(404, {"error": {"type": "not_found_error", "message": "model: %s not found" % model}})
                if "NANWAIT" in text:
                    return self.json(429, {"error": {"type": "rate_limit_error", "message": "Rate limit reached"}}, {"Retry-After": "nan"})
                if "RATE" in text:
                    return self.json(429, {"error": {"type": "rate_limit_error", "message": "Rate limit reached"}}, {"Retry-After": "7"})
                calls = [(m.group(1), json.loads(m.group(2) or "{}")) for m in re.finditer(r"^CALL (\w+) ?(\{.*\})?\s*$", text, re.M)]
                if "LOOP" in text:
                    calls = [("list_tabs", {})] * 1000
                if model == "plain-model" or not tools:
                    calls = []
                elif not calls and "still_test" in tools:  # Test connection's harmless tool
                    calls = [("still_test", {"say": "ok"})]
                turn = []
                if done < len(calls):
                    turn = calls[done:] if "MULTI" in text else [calls[done]]
                    turn = [(pick(tools, n), a) for n, a in turn]
                if turn:
                    answer = []
                else:
                    answer = ["Done. ", "Result: " + done_text(kind, body)[:120]] if calls else ["Hello ", "from the ", "fake model."]
                    if "SLOW" in text:
                        answer = ["word%d " % i for i in range(60)]
                stream = body.get("stream") or ":stream" in self.path
                usage = (2**63 - 1, 2**63 - 1) if "HUGE" in text else (1200 + len(json.dumps(body)) // 4, 40 + 7 * len(answer))
                return getattr(self, kind)(model, answer, turn, stream, usage, "SLOW" in text)

            def openai(self, model, answer, calls, stream, usage, slow):
                if not stream:
                    msg = {"role": "assistant", "content": "".join(answer) or None}
                    if calls:
                        msg["tool_calls"] = [{"id": "call_%d" % i, "type": "function", "function": {"name": n, "arguments": json.dumps(a)}} for i, (n, a) in enumerate(calls)]
                    return self.json(200, {"id": "c1", "object": "chat.completion", "model": model, "choices": [{"index": 0, "message": msg, "finish_reason": "tool_calls" if calls else "stop"}],
                        "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1], "total_tokens": sum(usage)}})
                self.sse()
                base = {"id": "c1", "object": "chat.completion.chunk", "model": model}
                self.event({**base, "choices": [{"index": 0, "delta": {"role": "assistant", "content": ""}}]})
                for piece in answer:
                    self.event({**base, "choices": [{"index": 0, "delta": {"content": piece}}]})
                    time.sleep(.5 if slow else .02)
                for i, (n, a) in enumerate(calls):
                    args = json.dumps(a)
                    self.event({**base, "choices": [{"index": 0, "delta": {"tool_calls": [{"index": i, "id": "call_%d_%d" % (i, time.time_ns() % 10**6), "type": "function", "function": {"name": n, "arguments": ""}}]}}]})
                    for part in (args[:len(args) // 2], args[len(args) // 2:]):
                        self.event({**base, "choices": [{"index": 0, "delta": {"tool_calls": [{"index": i, "function": {"arguments": part}}]}}]})
                self.event({**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls" if calls else "stop"}]})
                self.event({**base, "choices": [], "usage": {"prompt_tokens": usage[0], "completion_tokens": usage[1], "total_tokens": sum(usage)}})
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()

            def anthropic(self, model, answer, calls, stream, usage, slow):
                content = ([{"type": "text", "text": "".join(answer)}] if answer else []) + [{"type": "tool_use", "id": "toolu_%d_%d" % (i, time.time_ns() % 10**6), "name": n, "input": a} for i, (n, a) in enumerate(calls)]
                if not stream:
                    return self.json(200, {"id": "m1", "type": "message", "role": "assistant", "model": model, "content": content, "stop_reason": "tool_use" if calls else "end_turn",
                        "usage": {"input_tokens": usage[0], "output_tokens": usage[1]}})
                self.sse()
                self.event({"type": "message_start", "message": {"id": "m1", "type": "message", "role": "assistant", "model": model, "content": [], "usage": {"input_tokens": usage[0], "output_tokens": 1}}}, "message_start")
                for i, block in enumerate(content):
                    if block["type"] == "text":
                        self.event({"type": "content_block_start", "index": i, "content_block": {"type": "text", "text": ""}}, "content_block_start")
                        for piece in answer:
                            self.event({"type": "content_block_delta", "index": i, "delta": {"type": "text_delta", "text": piece}}, "content_block_delta")
                            time.sleep(.5 if slow else .02)
                    else:
                        self.event({"type": "content_block_start", "index": i, "content_block": {"type": "tool_use", "id": block["id"], "name": block["name"], "input": {}}}, "content_block_start")
                        args = json.dumps(block["input"])
                        for part in (args[:len(args) // 2], args[len(args) // 2:]):
                            self.event({"type": "content_block_delta", "index": i, "delta": {"type": "input_json_delta", "partial_json": part}}, "content_block_delta")
                    self.event({"type": "content_block_stop", "index": i}, "content_block_stop")
                self.event({"type": "message_delta", "delta": {"stop_reason": "tool_use" if calls else "end_turn"}, "usage": {"output_tokens": usage[1]}}, "message_delta")
                self.event({"type": "message_stop"}, "message_stop")

            def gemini(self, model, answer, calls, stream, usage, slow):
                meta = {"promptTokenCount": usage[0], "candidatesTokenCount": usage[1], "totalTokenCount": sum(usage)}
                parts = [{"text": "".join(answer)}] if answer else []
                parts += [{"functionCall": {"name": n, "args": a}} for n, a in calls]
                if not stream:
                    # Gemini CLI's own helper calls (next speaker, loop checks) ask for JSON: give the quietest answer.
                    if "json" in json.dumps(self.body.get("generationConfig") or {}).lower():
                        parts = [{"text": json.dumps({"next_speaker": "user", "reasoning": "The answer is complete."})}]
                    return self.json(200, {"candidates": [{"content": {"role": "model", "parts": parts or [{"text": ""}]}, "finishReason": "STOP", "index": 0}], "usageMetadata": meta, "modelVersion": model})
                self.sse()
                if answer:
                    for piece in answer:
                        self.event({"candidates": [{"content": {"role": "model", "parts": [{"text": piece}]}, "index": 0}], "modelVersion": model})
                        time.sleep(.5 if slow else .02)
                if calls:
                    self.event({"candidates": [{"content": {"role": "model", "parts": [{"functionCall": {"name": n, "args": a}} for n, a in calls]}, "index": 0}], "modelVersion": model})
                self.event({"candidates": [{"content": {"role": "model", "parts": [{"text": ""}]}, "finishReason": "STOP", "index": 0}], "usageMetadata": meta, "modelVersion": model})

        return H


def pick(tools, name):
    for t in tools:
        if t == name or t.endswith("_" + name):
            return t
    return name


def tool_names(kind, body):
    if kind == "gemini":
        return [f.get("name", "") for t in body.get("tools") or [] for f in t.get("functionDeclarations") or []]
    return [t.get("name") or (t.get("function") or {}).get("name", "") for t in body.get("tools") or []]


def text_of(content):
    if isinstance(content, str):
        return content
    return "\n".join(p.get("text", "") for p in content or [] if isinstance(p, dict) and p.get("type", "text") == "text")


def last_user(kind, body):
    """The last message the user typed, and how many tool results came after it."""
    msgs = body.get("messages") or body.get("contents") or []
    done = 0
    for m in reversed(msgs):
        if kind == "openai":
            if m.get("role") == "tool":
                done += 1
                continue
            if m.get("role") == "user":
                return text_of(m.get("content")), done
        elif kind == "anthropic":
            c = m.get("content")
            results = [p for p in c if isinstance(p, dict) and p.get("type") == "tool_result"] if isinstance(c, list) else []
            if m.get("role") == "user" and results:
                done += len(results)
                continue
            if m.get("role") == "user":
                return text_of(c), done
        else:
            parts = m.get("parts") or []
            if any("functionResponse" in p for p in parts):
                done += sum(1 for p in parts if "functionResponse" in p)
                continue
            if m.get("role") == "user" and any(p.get("text") for p in parts):
                return "\n".join(p.get("text", "") for p in parts), done
    return "", done


def done_text(kind, body):
    msgs = body.get("messages") or body.get("contents") or []
    last = msgs[-1] if msgs else {}
    if kind == "openai":
        return text_of(last.get("content"))
    if kind == "anthropic":
        for p in last.get("content") or []:
            if isinstance(p, dict) and p.get("type") == "tool_result":
                c = p.get("content")
                return c if isinstance(c, str) else text_of(c)
        return ""
    for p in last.get("parts") or []:
        if "functionResponse" in p:
            return json.dumps(p["functionResponse"].get("response"))
    return ""


if __name__ == "__main__":
    f = Fake(sys.argv[2] if len(sys.argv) > 2 else "test-key", int(sys.argv[1]) if len(sys.argv) > 1 else 0)
    print(f.url, flush=True)
    while True:
        time.sleep(3600)
