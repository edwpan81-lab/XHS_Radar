import json
import os
import re
import sys
from urllib.parse import urlparse

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


def normalize_doc_token(value: str) -> str:
    """Accept either a raw token or a Feishu/Lark docx URL."""
    parsed = urlparse(value)
    if parsed.scheme and parsed.netloc:
        match = re.search(r"/docx/([^/?#]+)", parsed.path)
        if match:
            return match.group(1)
    return value


def build_member(member_type: str, member_id: str, perm: str, include_optional: bool = True):
    member = {
        "member_type": member_type,
        "member_id": member_id,
        "perm": perm,
    }
    if include_optional:
        member["perm_type"] = "container"
        member["type"] = "user"
    return member


def add_member(token: str, document_id: str, member_type: str, member_id: str, perm: str, doc_type: str):
    errors: list[str] = []
    attempts = [
        (
            "batch_create_full",
            "POST",
            f"/drive/v1/permissions/{document_id}/members/batch_create?type={doc_type}&need_notification=false",
            {"members": [build_member(member_type, member_id, perm, include_optional=True)]},
        ),
        (
            "batch_create_minimal",
            "POST",
            f"/drive/v1/permissions/{document_id}/members/batch_create?type={doc_type}&need_notification=false",
            {"members": [build_member(member_type, member_id, perm, include_optional=False)]},
        ),
        (
            "single_full",
            "POST",
            f"/drive/v1/permissions/{document_id}/members?type={doc_type}",
            build_member(member_type, member_id, perm, include_optional=True),
        ),
        (
            "single_minimal",
            "POST",
            f"/drive/v1/permissions/{document_id}/members?type={doc_type}",
            build_member(member_type, member_id, perm, include_optional=False),
        ),
    ]
    for name, method, path, body in attempts:
        try:
            return name, api(method, path, token=token, json=body)
        except Exception as exc:
            error = str(exc)
            errors.append(f"{name}: {error}")
            if name.startswith("batch_create") and (
                "docs:permission.member" in error or "docs:permission.member:create" in error
            ):
                raise RuntimeError(
                    "Missing Feishu permission scope for adding document collaborators. "
                    "Open docs:permission.member or docs:permission.member:create in the Feishu app console, "
                    "publish the app permission change, then rerun this command.\n"
                    + error
                )
            if "email doesn't exist" in error:
                raise RuntimeError(
                    "The email passed to Feishu does not exist in this Feishu tenant. "
                    "Set FEISHU_REPORT_USER_EMAIL to the user's Feishu workplace login email, "
                    "or pass an explicit open_id/user_id instead, for example:\n"
                    "  python scripts\\share_feishu_doc.py DOCUMENT_ID openid OPEN_ID full_access\n"
                    "  python scripts\\share_feishu_doc.py DOCUMENT_ID userid USER_ID full_access\n"
                    "You can also try resolving an email first:\n"
                    "  python scripts\\share_feishu_doc.py --resolve-email user@example.com\n"
                    + error
                )
    raise RuntimeError("All permission add attempts failed:\n" + "\n".join(errors))


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
            json={
                "emails": emails or [],
                "mobiles": mobiles or [],
                "include_resigned": True,
            },
        )
    except Exception as exc:
        error = str(exc)
        if "contact:user.id:readonly" in error:
            raise RuntimeError(
                "Resolving an email/mobile to a Feishu user ID requires the app scope "
                "contact:user.id:readonly. Open that scope in the Feishu app console, "
                "publish the permission change, then rerun the resolve command. "
                "Alternatively, pass an existing open_id/user_id directly."
            ) from exc
        raise
    users = payload.get("data", {}).get("user_list", [])
    if not users:
        raise RuntimeError(
            "No Feishu user was found for that email/mobile. Use the user's Feishu workplace login email or phone number, "
            "or add the user to the app's contact visibility range."
        )
    return users[0]


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == "--resolve-email":
        user = resolve_contact_id(
            get_tenant_token(),
            emails=[sys.argv[2]],
            user_id_type=sys.argv[3] if len(sys.argv) > 3 else "open_id",
        )
        print(json.dumps(user, ensure_ascii=False))
        return

    if len(sys.argv) >= 3 and sys.argv[1] == "--resolve-mobile":
        user = resolve_contact_id(
            get_tenant_token(),
            mobiles=[sys.argv[2]],
            user_id_type=sys.argv[3] if len(sys.argv) > 3 else "open_id",
        )
        print(json.dumps(user, ensure_ascii=False))
        return

    if len(sys.argv) < 2:
        raise SystemExit(
            "Usage: python scripts/share_feishu_doc.py <document_id_or_url> [email|openid|unionid|userid] [member_id] [view|edit|full_access] [docx|doc|sheet|file|bitable]\n"
            "       python scripts/share_feishu_doc.py --resolve-email user@example.com [open_id|user_id|union_id]\n"
            "       python scripts/share_feishu_doc.py --resolve-mobile 13800138000 [open_id|user_id|union_id]"
        )

    document_id = normalize_doc_token(sys.argv[1])
    member_type = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("FEISHU_REPORT_MEMBER_TYPE")
    member_id = sys.argv[3] if len(sys.argv) > 3 else None
    perm = sys.argv[4] if len(sys.argv) > 4 else os.environ.get("FEISHU_REPORT_USER_PERM", "full_access")
    doc_type = sys.argv[5] if len(sys.argv) > 5 else os.environ.get("FEISHU_REPORT_DOC_TYPE", "docx")

    if not member_type:
        if os.environ.get("FEISHU_REPORT_USER_MOBILE"):
            member_type = "mobile"
            member_id = member_id or os.environ.get("FEISHU_REPORT_USER_MOBILE")
        else:
            member_type = "email"
            member_id = member_id or os.environ.get("FEISHU_REPORT_USER_EMAIL")

    if not member_id:
        raise RuntimeError("Pass member_id or set FEISHU_REPORT_USER_EMAIL / FEISHU_REPORT_USER_MOBILE")

    if member_type == "mobile":
        user = resolve_contact_id(token=get_tenant_token(), mobiles=[member_id], user_id_type="open_id")
        member_type = "openid"
        member_id = user.get("user_id")
        if not member_id:
            raise RuntimeError(f"Could not resolve mobile to open_id: {json.dumps(user, ensure_ascii=False)}")

    token = get_tenant_token()
    method_name, payload = add_member(token, document_id, member_type, member_id, perm, doc_type)
    print(json.dumps({"attempt": method_name, "data": payload.get("data", payload)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
