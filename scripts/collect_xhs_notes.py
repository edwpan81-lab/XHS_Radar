import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


DEFAULT_PROTOCOL_VERSION = "2024-11-05"


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
        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {},
        }
        self._write(payload)
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
        if not self.proc.stdin:
            raise RuntimeError("MCP stdin is closed")
        self.proc.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def _read(self) -> dict[str, Any]:
        if not self.proc.stdout:
            raise RuntimeError("MCP stdout is closed")
        line = self.proc.stdout.readline()
        if not line:
            stderr = self.proc.stderr.read() if self.proc.stderr else ""
            raise RuntimeError(f"MCP server exited unexpectedly: {stderr}")
        return json.loads(line)


def parse_tool_text(result: Any) -> Any:
    if not isinstance(result, dict):
        return result
    content = result.get("content")
    if not isinstance(content, list):
        return result
    texts = []
    for item in content:
        if isinstance(item, dict) and item.get("type") == "text":
            texts.append(item.get("text", ""))
    joined = "\n".join(texts).strip()
    if not joined:
        return result
    try:
        return json.loads(joined)
    except json.JSONDecodeError:
        return joined


def call_tool(client: McpClient, name: str, arguments: dict[str, Any]) -> Any:
    result = client.request("tools/call", {"name": name, "arguments": arguments})
    return parse_tool_text(result)


def load_keywords(path: Path) -> tuple[list[dict[str, Any]], int, int]:
    config = json.loads(path.read_text(encoding="utf-8"))
    return (
        config.get("keywords", []),
        int(config.get("default_limit_per_keyword", 5)),
        int(config.get("pause_seconds", 6)),
    )


def main():
    parser = argparse.ArgumentParser(description="Collect small Xiaohongshu samples through RedNote-MCP.")
    parser.add_argument("--config", default="config/xhs_keywords.example.json")
    parser.add_argument("--out", default="data/xhs_raw/xhs_notes.json")
    parser.add_argument("--detail-limit", type=int, default=0, help="Read details for the first N notes per keyword.")
    parser.add_argument("--command", default="rednote-mcp")
    args = parser.parse_args()

    keywords, default_limit, pause_seconds = load_keywords(Path(args.config))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    client = McpClient([args.command, "--stdio"])
    collected: list[dict[str, Any]] = []
    try:
        client.request(
            "initialize",
            {
                "protocolVersion": DEFAULT_PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "xhs-radar", "version": "0.1.0"},
            },
        )
        client.notify("notifications/initialized")

        for item in keywords:
            query = item["query"]
            limit = int(item.get("limit", default_limit))
            print(f"Searching: {query}", file=sys.stderr)
            search_result = call_tool(client, "search_notes", {"keywords": query, "limit": limit})
            record = {
                "keyword": query,
                "name": item.get("name"),
                "purpose": item.get("purpose"),
                "search_result": search_result,
                "details": [],
            }

            urls = extract_urls(search_result)[: args.detail_limit]
            for url in urls:
                time.sleep(pause_seconds)
                try:
                    detail = call_tool(client, "get_note_content", {"url": url})
                    record["details"].append({"url": url, "detail": detail})
                except Exception as exc:
                    record["details"].append({"url": url, "error": str(exc)})

            collected.append(record)
            time.sleep(pause_seconds)
    finally:
        client.close()

    out_path.write_text(json.dumps(collected, ensure_ascii=False, indent=2), encoding="utf-8")
    print(str(out_path))


def extract_urls(value: Any) -> list[str]:
    urls: list[str] = []
    if isinstance(value, str):
        for token in value.replace("\n", " ").split():
            if token.startswith("https://www.xiaohongshu.com/"):
                urls.append(token)
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


if __name__ == "__main__":
    main()
