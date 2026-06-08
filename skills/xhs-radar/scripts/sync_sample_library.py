import argparse
import json
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests

if os.name == "nt":
    import winreg


BASE_URL = "https://open.feishu.cn/open-apis"

FIELD_TYPES = {
    "标题": 1,
    "作者": 1,
    "链接": 1,
    "关键词": 1,
    "主题": 1,
    "点赞": 2,
    "评论": 2,
    "互动信号": 1,
    "样本类型": 1,
    "选题模型": 1,
    "平台适配": 1,
    "粉丝状态": 1,
    "采集日期": 1,
    "报告来源": 1,
    "备注": 1,
}


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


def require_env(name: str) -> str:
    value = get_env(name)
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
            f"{method} {path} failed: status={response.status_code}, payload={json.dumps(payload, ensure_ascii=False)[:1600]}"
        )
    return payload


def get_tenant_token() -> str:
    payload = api(
        "POST",
        "/auth/v3/tenant_access_token/internal",
        json={"app_id": require_env("FEISHU_APP_ID"), "app_secret": require_env("FEISHU_APP_SECRET")},
    )
    token = payload.get("tenant_access_token") or payload.get("data", {}).get("tenant_access_token")
    if not token:
        raise RuntimeError("Feishu token response did not include tenant_access_token")
    return token


def create_bitable_app(token: str, name: str) -> str:
    body = {"name": name}
    folder_token = get_env("FEISHU_SAMPLE_FOLDER_TOKEN") or get_env("FEISHU_REPORT_FOLDER_TOKEN")
    if folder_token:
        body["folder_token"] = folder_token
    payload = api("POST", "/bitable/v1/apps", token=token, json=body)
    app = payload.get("data", {}).get("app", payload.get("data", {}))
    app_token = app.get("app_token") or app.get("token") or payload.get("data", {}).get("app_token")
    if not app_token:
        raise RuntimeError(f"Could not find app_token in response: {json.dumps(payload, ensure_ascii=False)[:800]}")
    return app_token


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
    payload = api(
        "POST",
        f"/contact/v3/users/batch_get_id?user_id_type={user_id_type}",
        token=token,
        json={"emails": emails or [], "mobiles": mobiles or [], "include_resigned": True},
    )
    users = payload.get("data", {}).get("user_list", [])
    if not users:
        raise RuntimeError("No Feishu user was found for that email/mobile.")
    return users[0]


def add_bitable_collaborator(token: str, app_token: str):
    perm = get_env("FEISHU_REPORT_USER_PERM", "full_access")
    mobile = get_env("FEISHU_REPORT_USER_MOBILE")
    if mobile:
        user = resolve_contact_id(token, mobiles=[mobile], user_id_type="open_id")
        member_id = user.get("user_id")
        if not member_id:
            raise RuntimeError(f"Could not resolve mobile to open_id: {json.dumps(user, ensure_ascii=False)}")
        member_type = "openid"
    else:
        member_type = get_env("FEISHU_REPORT_MEMBER_TYPE") or "email"
        member_id = get_env("FEISHU_REPORT_MEMBER_ID") or get_env("FEISHU_REPORT_USER_EMAIL")
    if not member_id:
        return None

    attempts = [
        (
            "batch_create_full",
            f"/drive/v1/permissions/{app_token}/members/batch_create?type=bitable&need_notification=false",
            {"members": [build_member(member_type, member_id, perm, include_optional=True)]},
        ),
        (
            "batch_create_minimal",
            f"/drive/v1/permissions/{app_token}/members/batch_create?type=bitable&need_notification=false",
            {"members": [build_member(member_type, member_id, perm, include_optional=False)]},
        ),
    ]
    errors: list[str] = []
    for name, path, body in attempts:
        try:
            payload = api("POST", path, token=token, json=body)
            return {"attempt": name, "data": payload.get("data", payload)}
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    raise RuntimeError("Failed to add Bitable collaborator:\n" + "\n".join(errors))


def create_sample_table(token: str, app_token: str, table_name: str) -> str:
    fields = [
        {"field_name": name, "type": field_type}
        for name, field_type in FIELD_TYPES.items()
        if name != "标题"
    ]
    body = {
        "table": {
            "name": table_name,
            "default_view_name": "全部样本",
            "fields": [
                {"field_name": "标题", "type": 1, "is_primary": True},
                *fields,
            ],
        }
    }
    payload = api("POST", f"/bitable/v1/apps/{app_token}/tables", token=token, json=body)
    table = payload.get("data", {}).get("table", payload.get("data", {}))
    table_id = table.get("table_id")
    if not table_id:
        raise RuntimeError(f"Could not find table_id in response: {json.dumps(payload, ensure_ascii=False)[:800]}")
    return table_id


def list_records(token: str, app_token: str, table_id: str) -> list[dict]:
    records: list[dict] = []
    page_token = None
    while True:
        path = f"/bitable/v1/apps/{app_token}/tables/{table_id}/records?page_size=500"
        if page_token:
            path += f"&page_token={page_token}"
        payload = api("GET", path, token=token)
        data = payload.get("data", {})
        records.extend(data.get("items", []))
        if not data.get("has_more"):
            break
        page_token = data.get("page_token")
    return records


def batch_create_records(token: str, app_token: str, table_id: str, rows: list[dict]):
    created = []
    for start in range(0, len(rows), 500):
        batch = rows[start : start + 500]
        payload = api(
            "POST",
            f"/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create",
            token=token,
            json={"records": [{"fields": row} for row in batch]},
        )
        created.extend(payload.get("data", {}).get("records", []))
        time.sleep(0.3)
    return created


def parse_report_samples(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    rows = []
    in_table = False
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("| 样本 | 标题 | 作者 |"):
            in_table = True
            continue
        if in_table and line.startswith("|---"):
            continue
        if in_table and not line.startswith("|"):
            break
        if not in_table:
            continue
        cells = split_markdown_row(line)
        if len(cells) < 7:
            continue
        _, title, author, likes, comments, signal, link = cells[:7]
        rows.append(
            normalize_sample(
                {
                    "标题": title.replace("\\|", "|"),
                    "作者": author,
                    "链接": link,
                    "关键词": infer_keyword(text),
                    "主题": infer_topic(text),
                    "点赞": to_number(likes),
                    "评论": to_number(comments),
                    "互动信号": signal,
                    "样本类型": classify_sample(title, signal),
                    "选题模型": infer_model(title, signal),
                    "平台适配": infer_platform_fit(title, signal),
                    "粉丝状态": "待复核",
                    "采集日期": infer_report_date(path, text),
                    "报告来源": path.name,
                    "备注": "",
                }
            )
        )
    if not rows:
        raise RuntimeError(f"No sample table rows found in {path}")
    return rows


def split_markdown_row(line: str) -> list[str]:
    stripped = line.strip().strip("|")
    cells = re.split(r"(?<!\\)\|", stripped)
    return [cell.strip() for cell in cells]


def normalize_sample(row: dict) -> dict:
    normalized = {}
    for key in FIELD_TYPES:
        value = row.get(key, "")
        if FIELD_TYPES[key] == 2:
            normalized[key] = to_number(value)
        else:
            normalized[key] = "" if value is None else str(value)
    return normalized


def to_number(value) -> int | float:
    if isinstance(value, (int, float)):
        return value
    text = str(value).replace(",", "").strip()
    try:
        number = float(text)
        return int(number) if number.is_integer() else number
    except ValueError:
        return 0


def infer_keyword(text: str) -> str:
    match = re.search(r"搜索关键词：(.+?)。", text)
    if match:
        return match.group(1)
    return "泡泡玛特"


def infer_topic(text: str) -> str:
    first_line = next((line.strip("# ").strip() for line in text.splitlines() if line.startswith("# ")), "")
    if "泡泡玛特" in first_line:
        return "泡泡玛特"
    return first_line or "未分类"


def infer_report_date(path: Path, text: str) -> str:
    match = re.search(r"(20\d{2}-\d{2}-\d{2})", path.name) or re.search(r"(20\d{2}-\d{2}-\d{2})", text)
    return match.group(1) if match else date.today().isoformat()


def classify_sample(title: str, signal: str) -> str:
    combined = title + " " + signal
    if any(word in combined for word in ["门店", "服务", "自提"]):
        return "品牌体验争议型"
    if any(word in combined for word in ["手感", "攻略", "重量", "可执行"]):
        return "实用攻略型"
    if any(word in combined for word in ["虚假", "落差", "避雷", "上当", "争议"]):
        return "预期落差/避雷型"
    if any(word in combined for word in ["为什么", "理解", "羞耻", "永远赚不到", "情绪"]):
        return "情绪反转/消费心理型"
    return "高互动样本"


def infer_model(title: str, signal: str) -> str:
    sample_type = classify_sample(title, signal)
    mapping = {
        "实用攻略型": "决策攻略模型",
        "预期落差/避雷型": "预期落差模型",
        "情绪反转/消费心理型": "情绪反转模型",
        "品牌体验争议型": "体验摩擦模型",
    }
    return mapping.get(sample_type, "待归纳")


def infer_platform_fit(title: str, signal: str) -> str:
    combined = title + " " + signal
    if any(word in combined for word in ["商业", "品牌", "消费心理", "服务分析", "讨论题"]):
        return "公众号 + 小红书"
    return "小红书优先"


def ensure_library(
    token: str,
    app_name: str,
    table_name: str,
    app_token_arg: str | None = None,
    table_id_arg: str | None = None,
) -> tuple[str, str, bool]:
    app_token = app_token_arg or get_env("FEISHU_SAMPLE_BASE_APP_TOKEN") or get_env("FEISHU_BITABLE_APP_TOKEN")
    table_id = table_id_arg or get_env("FEISHU_SAMPLE_TABLE_ID") or get_env("FEISHU_BITABLE_TABLE_ID")
    created = False
    if not app_token:
        app_token = create_bitable_app(token, app_name)
        created = True
    if not table_id:
        table_id = create_sample_table(token, app_token, table_name)
        created = True
    return app_token, table_id, created


def main():
    parser = argparse.ArgumentParser(description="Sync XHS samples into a Feishu Bitable sample library.")
    parser.add_argument("--report", default="reports/popmart_mvp_2026-06-07.md")
    parser.add_argument("--app-name", default="XHS Radar 样本库")
    parser.add_argument("--table-name", default="小红书样本库")
    parser.add_argument("--app-token", default=None)
    parser.add_argument("--table-id", default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    samples = parse_report_samples(Path(args.report))
    token = get_tenant_token()
    app_token, table_id, created_library = ensure_library(
        token,
        args.app_name,
        args.table_name,
        app_token_arg=args.app_token,
        table_id_arg=args.table_id,
    )

    existing_links = set()
    try:
        for record in list_records(token, app_token, table_id):
            fields = record.get("fields", {})
            link_value = fields.get("链接", "")
            if isinstance(link_value, list):
                link_value = "".join(str(part.get("text", part)) for part in link_value if isinstance(part, dict))
            existing_links.add(str(link_value))
    except Exception as exc:
        print(f"Could not list existing records; continuing with append-only sync: {exc}", file=sys.stderr)

    new_samples = [sample for sample in samples if sample.get("链接") not in existing_links]
    result = {
        "app_token": app_token,
        "table_id": table_id,
        "created_library": created_library,
        "parsed_samples": len(samples),
        "existing_matches": len(samples) - len(new_samples),
        "to_create": len(new_samples),
        "url": f"https://feishu.cn/base/{app_token}?table={table_id}",
    }
    try:
        collaborator = add_bitable_collaborator(token, app_token)
        if collaborator:
            result["collaborator"] = collaborator
    except Exception as exc:
        result["collaborator_error"] = str(exc)
        print(f"Collaborator add failed: {exc}", file=sys.stderr)

    if args.dry_run:
        result["preview"] = new_samples[:3]
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return

    if new_samples:
        created = batch_create_records(token, app_token, table_id, new_samples)
        result["created_records"] = len(created)
    else:
        result["created_records"] = 0
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
