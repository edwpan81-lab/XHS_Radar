import json
import os
import sys
import time
from pathlib import Path

import requests


BASE_URL = "https://open.feishu.cn/open-apis"


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


def api(method: str, path: str, token: str | None = None, **kwargs):
    headers = kwargs.pop("headers", {})
    headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    response = requests.request(method, BASE_URL + path, headers=headers, timeout=30, **kwargs)
    try:
        payload = response.json()
    except Exception:
        payload = {"raw": response.text}
    if response.status_code >= 400 or payload.get("code", 0) != 0:
        raise RuntimeError(
            f"{method} {path} failed: status={response.status_code}, payload={json.dumps(payload, ensure_ascii=False)[:1200]}"
        )
    return payload


def get_tenant_token() -> str:
    payload = api(
        "POST",
        "/auth/v3/tenant_access_token/internal",
        json={
            "app_id": require_env("FEISHU_APP_ID"),
            "app_secret": require_env("FEISHU_APP_SECRET"),
        },
    )
    token = payload.get("tenant_access_token") or payload.get("data", {}).get("tenant_access_token")
    if not token:
        raise RuntimeError("Feishu token response did not include tenant_access_token")
    return token


def create_document(token: str, title: str) -> str:
    body = {"title": title}
    folder_token = os.environ.get("FEISHU_REPORT_FOLDER_TOKEN")
    if folder_token:
        body["folder_token"] = folder_token
    payload = api("POST", "/docx/v1/documents", token=token, json=body)
    return payload["data"]["document"]["document_id"]


def markdown_to_blocks(token: str, document_id: str, markdown: str):
    candidates = [
        f"/docx/v1/documents/{document_id}/convert",
        "/docx/v1/documents/blocks/convert",
    ]
    errors: list[str] = []
    for path in candidates:
        try:
            payload = api(
                "POST",
                path,
                token=token,
                json={"content": markdown, "content_type": "markdown"},
            )
            data = payload.get("data", {})
            blocks = data.get("blocks") or data.get("children") or data.get("items")
            if blocks:
                return blocks
            errors.append(f"{path}: no blocks in {json.dumps(data, ensure_ascii=False)[:500]}")
        except Exception as exc:
            errors.append(f"{path}: {exc}")
    raise RuntimeError("Markdown convert failed:\n" + "\n".join(errors))


def fallback_text_blocks(markdown: str):
    blocks = []
    for raw in markdown.splitlines():
        line = raw.strip()
        if not line:
            continue
        block_type = 2
        key = "text"
        content = line
        if line.startswith("# "):
            block_type, key, content = 3, "heading1", line[2:]
        elif line.startswith("## "):
            block_type, key, content = 4, "heading2", line[3:]
        elif line.startswith("### "):
            block_type, key, content = 5, "heading3", line[4:]
        elif line.startswith("- "):
            block_type, key, content = 12, "bullet", line[2:]
        blocks.append(
            {
                "block_type": block_type,
                key: {
                    "elements": [
                        {
                            "text_run": {
                                "content": content,
                                "text_element_style": {},
                            }
                        }
                    ],
                    "style": {},
                },
            }
        )
    return blocks


def append_blocks(token: str, document_id: str, blocks):
    path = f"/docx/v1/documents/{document_id}/blocks/{document_id}/children"
    for start in range(0, len(blocks), 50):
        api("POST", path, token=token, json={"children": blocks[start : start + 50], "index": -1})
        time.sleep(0.5)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python create_feishu_report.py <markdown-file>")
    report_path = Path(sys.argv[1])
    markdown = report_path.read_text(encoding="utf-8")
    token = get_tenant_token()
    document_id = create_document(token, report_path.stem.replace("_", " "))
    try:
        blocks = markdown_to_blocks(token, document_id, markdown)
    except Exception as exc:
        print(f"Markdown convert unavailable, falling back to plain blocks: {exc}", file=sys.stderr)
        blocks = fallback_text_blocks(markdown)
    append_blocks(token, document_id, blocks)
    print(json.dumps({"document_id": document_id, "url": f"https://feishu.cn/docx/{document_id}"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
