import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


class McpClient:
    def __init__(self, command: list[str]):
        self.proc = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        self._next_id = 1

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.proc.kill()

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        request_id = self._next_id
        self._next_id += 1
        self._write({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}})
        while True:
            message = self._read()
            if message.get("id") != request_id:
                continue
            if "error" in message:
                raise RuntimeError(json.dumps(message["error"], ensure_ascii=False))
            return message.get("result")

    def notify(self, method: str, params: dict[str, Any] | None = None):
        self._write({"jsonrpc": "2.0", "method": method, "params": params or {}})

    def _write(self, payload: dict[str, Any]):
        self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def _read(self) -> dict[str, Any]:
        line = self.proc.stdout.readline()
        if not line:
            stderr = self.proc.stderr.read() if self.proc.stderr else ""
            raise RuntimeError(f"MCP server exited unexpectedly: {stderr}")
        return json.loads(line)


def parse_tool_text(result: Any) -> Any:
    content = result.get("content") if isinstance(result, dict) else None
    if not isinstance(content, list):
        return result
    text = "\n".join(item.get("text", "") for item in content if isinstance(item, dict) and item.get("type") == "text").strip()
    if not text:
        return result
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def call_tool(client: McpClient, name: str, arguments: dict[str, Any]) -> Any:
    return parse_tool_text(client.request("tools/call", {"name": name, "arguments": arguments}))


def extract_urls(value: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(value, str):
        urls.extend(token for token in value.replace("\n", " ").split() if token.startswith("https://www.xiaohongshu.com/"))
    elif isinstance(value, list):
        for item in value:
            urls.extend(extract_urls(item))
    elif isinstance(value, dict):
        for key, item in value.items():
            if key == "url" and isinstance(item, str):
                urls.append(item)
            else:
                urls.extend(extract_urls(item))
    return list(dict.fromkeys(urls))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="config/xhs_keywords.example.json")
    parser.add_argument("--out", default="data/xhs_raw/xhs_notes.json")
    parser.add_argument("--detail-limit", type=int, default=0)
    parser.add_argument("--command", default="rednote-mcp")
    args = parser.parse_args()

    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    client = McpClient([args.command, "--stdio"])
    records = []
    try:
        client.request("initialize", {"protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "xhs-radar", "version": "0.1.0"}})
        client.notify("notifications/initialized")
        for item in config.get("keywords", []):
            query = item["query"]
            limit = int(item.get("limit", config.get("default_limit_per_keyword", 5)))
            pause = int(config.get("pause_seconds", 6))
            print(f"Searching: {query}", file=sys.stderr)
            search_result = call_tool(client, "search_notes", {"keywords": query, "limit": limit})
            record = {"keyword": query, "search_result": search_result, "details": []}
            for url in extract_urls(search_result)[: args.detail_limit]:
                time.sleep(pause)
                record["details"].append({"url": url, "detail": call_tool(client, "get_note_content", {"url": url})})
            records.append(record)
            time.sleep(pause)
    finally:
        client.close()

    out_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))


if __name__ == "__main__":
    main()
