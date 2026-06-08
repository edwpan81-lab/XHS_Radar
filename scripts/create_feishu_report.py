import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlparse
if os.name == "nt":
    import winreg

import requests


BASE_URL = "https://open.feishu.cn/open-apis"


def require_env(name: str) -> str:
    value = get_env(name)
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


def get_env(name: str, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if value:
        return value
    if os.name == "nt":
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
                value, _ = winreg.QueryValueEx(key, name)
                if value:
                    return str(value)
        except OSError:
            pass
    return default


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
    app_id = require_env("FEISHU_APP_ID")
    app_secret = require_env("FEISHU_APP_SECRET")
    payload = api(
        "POST",
        "/auth/v3/tenant_access_token/internal",
        json={"app_id": app_id, "app_secret": app_secret},
    )
    token = payload.get("tenant_access_token") or payload.get("data", {}).get("tenant_access_token")
    if not token:
        raise RuntimeError("Feishu token response did not include tenant_access_token")
    return token


def create_document(token: str, title: str) -> str:
    body = {"title": title}
    folder_token = get_env("FEISHU_REPORT_FOLDER_TOKEN")
    if folder_token:
        body["folder_token"] = folder_token
    payload = api("POST", "/docx/v1/documents", token=token, json=body)
    return payload["data"]["document"]["document_id"]


def normalize_doc_token(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        match = re.search(r"/docx/([^/?#]+)", parsed.path)
        if match:
            return match.group(1)
    return value


def build_member(member_type: str, member_id: str, perm: str, include_optional: bool = True):
    member = {"member_type": member_type, "member_id": member_id, "perm": perm}
    if include_optional:
        member["perm_type"] = "container"
        member["type"] = "user"
    return member


def resolve_contact_id(
    token: str,
    *,
    emails: list[str] | None = None,
    mobiles: list[str] | None = None,
    user_id_type: str = "open_id",
):
    try:
        payload = api(
            "POST",
            f"/contact/v3/users/batch_get_id?user_id_type={user_id_type}",
            token=token,
            json={"emails": emails or [], "mobiles": mobiles or [], "include_resigned": True},
        )
    except Exception as exc:
        error = str(exc)
        if "contact:user.id:readonly" in error:
            raise RuntimeError(
                "Resolving an email/mobile to a Feishu user ID requires the app scope "
                "contact:user.id:readonly. Open that scope in the Feishu app console, "
                "publish the permission change, then rerun."
            ) from exc
        raise
    users = payload.get("data", {}).get("user_list", [])
    if not users:
        raise RuntimeError("No Feishu user was found for that email/mobile.")
    return users[0]


def add_member(token: str, document_id: str, member_type: str, member_id: str, perm: str, doc_type: str):
    attempts = [
        (
            "batch_create_full",
            f"/drive/v1/permissions/{document_id}/members/batch_create?type={doc_type}&need_notification=false",
            {"members": [build_member(member_type, member_id, perm, include_optional=True)]},
        ),
        (
            "batch_create_minimal",
            f"/drive/v1/permissions/{document_id}/members/batch_create?type={doc_type}&need_notification=false",
            {"members": [build_member(member_type, member_id, perm, include_optional=False)]},
        ),
    ]
    errors: list[str] = []
    for name, path, body in attempts:
        try:
            return name, api("POST", path, token=token, json=body)
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    raise RuntimeError("Failed to add Feishu collaborator:\n" + "\n".join(errors))


def collaborator_from_env(token: str):
    perm = get_env("FEISHU_REPORT_USER_PERM", "full_access")
    doc_type = get_env("FEISHU_REPORT_DOC_TYPE", "docx")

    mobile = get_env("FEISHU_REPORT_USER_MOBILE")
    if mobile:
        user = resolve_contact_id(token, mobiles=[mobile], user_id_type="open_id")
        member_id = user.get("user_id")
        if not member_id:
            raise RuntimeError(f"Could not resolve mobile to open_id: {json.dumps(user, ensure_ascii=False)}")
        return "openid", member_id, perm, doc_type

    member_type = get_env("FEISHU_REPORT_MEMBER_TYPE")
    member_id = get_env("FEISHU_REPORT_MEMBER_ID")
    if member_type and member_id:
        return member_type, member_id, perm, doc_type

    email = get_env("FEISHU_REPORT_USER_EMAIL")
    if email:
        return "email", email, perm, doc_type

    return None


def maybe_add_collaborator(token: str, document_id: str):
    collaborator = collaborator_from_env(token)
    if not collaborator:
        return None
    member_type, member_id, perm, doc_type = collaborator
    method_name, payload = add_member(token, normalize_doc_token(document_id), member_type, member_id, perm, doc_type)
    return {"attempt": method_name, "data": payload.get("data", payload)}


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
        batch = blocks[start : start + 50]
        api("POST", path, token=token, json={"children": batch, "index": -1})
        time.sleep(0.5)


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/create_feishu_report.py <markdown-file>")
    report_path = Path(sys.argv[1])
    markdown = report_path.read_text(encoding="utf-8")
    title = report_path.stem.replace("_", " ")
    token = get_tenant_token()
    document_id = create_document(token, title)
    try:
        blocks = markdown_to_blocks(token, document_id, markdown)
    except Exception as exc:
        print(f"Markdown convert unavailable, falling back to plain blocks: {exc}", file=sys.stderr)
        blocks = fallback_text_blocks(markdown)
    append_blocks(token, document_id, blocks)
    result = {"document_id": document_id, "url": f"https://feishu.cn/docx/{document_id}"}
    try:
        collaborator = maybe_add_collaborator(token, document_id)
        if collaborator:
            result["collaborator"] = collaborator
    except Exception as exc:
        result["collaborator_error"] = str(exc)
        print(f"Collaborator add failed: {exc}", file=sys.stderr)
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
