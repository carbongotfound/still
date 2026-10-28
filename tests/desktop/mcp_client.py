"""A minimal MCP client over stdio, like an AI app would run Still: `Still.exe --mcp --as <name>`."""
import json
import queue
import subprocess
import threading


class Mcp:
    """A minimal MCP client over stdio, like an AI app would run it."""
    def __init__(self, exe, name, profile):
        self.proc = subprocess.Popen([str(exe), "--qa", "--mcp", "--as", name, "--profile", str(profile), "--profiles-root", str(profile)],
                                     stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.replies, self.next = {}, 1
        self.lock = threading.Condition()
        threading.Thread(target=self._read, daemon=True).start()
        self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": name, "version": "1"}})
        self._write({"jsonrpc": "2.0", "method": "notifications/initialized"})
    def _read(self):
        for line in self.proc.stdout:
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            with self.lock:
                self.replies[message.get("id")] = message
                self.lock.notify_all()
    def _write(self, message):
        self.proc.stdin.write((json.dumps(message) + "\n").encode())
        self.proc.stdin.flush()
    def request(self, method, params, seconds=60):
        with self.lock:
            rid = self.next; self.next += 1
        self._write({"jsonrpc": "2.0", "id": rid, "method": method, "params": params})
        with self.lock:
            if not self.lock.wait_for(lambda: rid in self.replies, seconds):
                raise TimeoutError(method + " got no reply")
            return self.replies.pop(rid)
    def call(self, tool, seconds=60, **args):
        """Returns (ok, text) for one tool call."""
        result = self.request("tools/call", {"name": tool, "arguments": args}, seconds)["result"]
        text = "\n".join(c.get("text", "") for c in result.get("content", []))
        return not result.get("isError"), text
    def close(self):
        try:
            self.proc.stdin.close()
            self.proc.wait(timeout=10)
        except Exception:
            self.proc.kill()

def call_async(client, tool, **args):
    out = queue.Queue()
    threading.Thread(target=lambda: out.put(client.call(tool, **args)), daemon=True).start()
    return out
