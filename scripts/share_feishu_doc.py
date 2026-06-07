import json
import os
import sys

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


def main():
    if len(sys.argv) < 2:
        raise SystemExit(
            "Usage: python scripts/share_feishu_doc.py <document_id> [email|openid|unionid] [member_id] [view|edit|full_access]"
        )

    document_id = sys.argv[1]
    member_type = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("FEISHU_REPORT_MEMBER_TYPE", "email")
    member_id = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("FEISHU_REPORT_USER_EMAIL")
    perm = sys.argv[4] if len(sys.argv) > 4 else os.environ.get("FEISHU_REPORT_USER_PERM", "full_access")

    if not member_id:
        raise RuntimeError("Pass member_id or set FEISHU_REPORT_USER_EMAIL")

    token = get_tenant_token()
    payload = api(
        "POST",
        f"/drive/v1/permissions/{document_id}/members?type=docx",
        token=token,
        json={
            "member_type": member_type,
            "member_id": member_id,
            "perm": perm,
            "perm_type": "container",
            "type": "user",
        },
    )
    print(json.dumps(payload.get("data", payload), ensure_ascii=False))


if __name__ == "__main__":
    main()
