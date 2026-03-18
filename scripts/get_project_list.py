#!/usr/bin/env python3
"""Get project list using JWT from iamToken redirect or manual token."""

from __future__ import annotations

import argparse
import json
import ssl
import urllib.parse
import uuid
from collections import deque
from typing import Any
from urllib import error, request

PROJECT_API_URL = (
    "https://prod-itpm.faw.cn/itpmNew/gateway/sop-itpm-service/"
    "projectEstablishment/queryProjectEstablishmentList"
)
IAM_TOKEN_URL = "https://iwork.faw.cn/api-dev/dcp-base-sso/iamToken"
DEFAULT_CLIENT_ID = "faw_qfc_sso"
DEFAULT_SECRET_PATH = "iworkiamencrypt.client-secret"
DEFAULT_REDIRECT_URL = "https://iwork.faw.cn/api-dev/dcp-base-sso/iamToken"
DEFAULT_INDEX_URL = "https://iwork.faw.cn"
DEFAULT_TENANT_ID = "YQJT"
DEFAULT_SYSTEM_ID = "BA-0222"
DEFAULT_MENU_CODE = "null"
DEFAULT_LOGO = "iworkiamencrypt"
DEFAULT_STATE = "123"
DEFAULT_JSESSIONID = "j9QX89zUdXq06ebkkGaVg9wpZnX5aakB_nJ7Al4g"
DEFAULT_TOKEN = (
    "Bearer "
    "eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiJqaWFxaW5nYm8iLCJjcmVhdGVkIjoxNzcyNzc0Mjg2NTA2"
    "LCJpZG1pZCI6InUyMDE5MDA5MDEwIiwiZXhwIjoxNzczMzc5MDg2LCJ1cGtpZCI6IjE1NDQyMTcyOT"
    "gyNTYwMDMwNzQifQ.VoXRSdZl6NZZ2BBmeCkZgogeBymINRU0hnaVrCWUylv3C99UCs9XzpZcTbOY"
    "19rmLHKm9y288MQC87cNJ21wdQ"
)

LIKELY_LIST_KEYS = (
    "records",
    "list",
    "rows",
    "items",
    "projectList",
    "projectEstablishmentList",
    "content",
    "pageList",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Get project list from ITPM API.")
    parser.add_argument(
        "--token",
        default=DEFAULT_TOKEN,
        help="JWT token (default: built-in token). Accepts Bearer or raw token.",
    )
    parser.add_argument(
        "--use-iam",
        action="store_true",
        help="Fetch token from iamToken flow instead of --token.",
    )
    parser.add_argument(
        "--jsessionid",
        default=DEFAULT_JSESSIONID,
        help="JSESSIONID cookie value for iamToken flow.",
    )
    parser.add_argument(
        "--iam-full-url",
        default="",
        help="Full iamToken URL that already includes code/state params.",
    )
    parser.add_argument(
        "--iam-code",
        default="",
        help="Optional SSO callback code for iamToken endpoint.",
    )
    parser.add_argument("--iam-url", default=IAM_TOKEN_URL, help="iamToken endpoint.")
    parser.add_argument("--client-id", default=DEFAULT_CLIENT_ID)
    parser.add_argument("--secret-path", default=DEFAULT_SECRET_PATH)
    parser.add_argument("--redirect-url", default=DEFAULT_REDIRECT_URL)
    parser.add_argument("--index-url", default=DEFAULT_INDEX_URL)
    parser.add_argument("--tenant-id", default=DEFAULT_TENANT_ID)
    parser.add_argument("--system-id", default=DEFAULT_SYSTEM_ID)
    parser.add_argument("--menu-code", default=DEFAULT_MENU_CODE)
    parser.add_argument("--logo", default=DEFAULT_LOGO)
    parser.add_argument("--state", default=DEFAULT_STATE)
    parser.add_argument("--show-token", action="store_true", help="Print fetched JWT token.")
    parser.add_argument("--only-token", action="store_true", help="Only fetch/print token, skip project API.")
    parser.add_argument("--page-num", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=10)
    parser.add_argument("--payload-json", default="{}")
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument("--show-raw", action="store_true")
    return parser.parse_args()


def parse_json_object(raw_text: str) -> dict[str, Any]:
    value = json.loads(raw_text)
    if not isinstance(value, dict):
        raise ValueError("--payload-json must be JSON object.")
    return value


def normalize_bearer(token: str) -> str:
    token = token.strip()
    if token.lower().startswith("bearer "):
        return token
    return f"Bearer {token}"


def fetch_token_from_iam(args: argparse.Namespace) -> str:
    if args.iam_full_url:
        url = args.iam_full_url
    else:
        query = {
            "clientId": args.client_id,
            "secretPath": args.secret_path,
            "redirectUrl": args.redirect_url,
            "indexUrl": args.index_url,
            "tenantId": args.tenant_id,
            "systemId": args.system_id,
            "menuCode": args.menu_code,
            "logo": args.logo,
        }
        if args.iam_code:
            query["code"] = args.iam_code
            query["state"] = args.state
        url = f"{args.iam_url}?{urllib.parse.urlencode(query)}"
    headers = {
        "accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "referer": "https://iam.faw.cn/",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/145.0.0.0 Safari/537.36"
        ),
    }
    if args.jsessionid:
        headers["cookie"] = f"JSESSIONID={args.jsessionid}"
    req = request.Request(url=url, method="GET", headers=headers)
    context = ssl._create_unverified_context()

    redirect_url = ""
    try:
        with request.urlopen(req, timeout=args.timeout, context=context) as resp:
            redirect_url = resp.geturl()
    except error.HTTPError as exc:
        if exc.code in (301, 302, 303, 307, 308):
            redirect_url = exc.headers.get("Location", "")
        else:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"iamToken failed: HTTP {exc.code}, body={body}") from exc
    except Exception as exc:
        raise RuntimeError(f"iamToken request failed: {exc}") from exc

    if not redirect_url:
        raise RuntimeError(
            "iamToken has no redirect URL. If message says '缺少参数：code', "
            "please provide --iam-code or --iam-full-url (with code)."
        )

    parsed = urllib.parse.urlparse(redirect_url)
    params = urllib.parse.parse_qs(parsed.query)
    token = (params.get("token") or [""])[0].strip()
    if not token:
        raise RuntimeError(
            "token not found in redirect URL. "
            "Make sure iamToken request includes valid code."
        )
    return token


def build_project_headers(token: str) -> dict[str, str]:
    return {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9",
        "authorization": normalize_bearer(token),
        "content-type": "application/json",
        "gray": "",
        "lang": "zh-cn",
        "origin": "https://iwork.faw.cn",
        "qfc-user-para": '{"systemId":"MS-0701","appCode":"MS-0701_APP_004"}',
        "qfcsid": "MS-0701",
        "qfctid": "YQJT",
        "referer": "https://iwork.faw.cn/",
        "sw8": "",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/145.0.0.0 Safari/537.36"
        ),
        "useragent": "pc",
        "x-traceid": uuid.uuid4().hex[:16],
    }


def request_project_list(token: str, payload: dict[str, Any], timeout: int) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        url=PROJECT_API_URL,
        method="POST",
        headers=build_project_headers(token),
        data=body,
    )
    context = ssl._create_unverified_context()
    with request.urlopen(req, timeout=timeout, context=context) as resp:
        return json.loads(resp.read().decode("utf-8", errors="replace"))


def find_project_list(data: Any) -> list[Any] | None:
    if isinstance(data, list):
        return data
    if not isinstance(data, dict):
        return None

    for key in LIKELY_LIST_KEYS:
        value = data.get(key)
        if isinstance(value, list):
            return value

    queue: deque[Any] = deque([data])
    while queue:
        current = queue.popleft()
        if isinstance(current, dict):
            for value in current.values():
                if isinstance(value, list) and (
                    not value or isinstance(value[0], (dict, list))
                ):
                    return value
                if isinstance(value, dict):
                    queue.append(value)
    return None


def main() -> int:
    args = parse_args()

    try:
        extra = parse_json_object(args.payload_json)
    except Exception as exc:
        print(f"invalid payload-json: {exc}")
        return 2

    token = args.token
    if args.use_iam:
        try:
            token = fetch_token_from_iam(args)
            if args.jsessionid:
                print("iam token fetch by JSESSIONID: success")
            else:
                print("iam token fetch: success")
        except Exception as exc:
            print(f"iam token fetch failed: {exc}")
            return 1

    if not token:
        print("missing token: provide --token or valid --jsessionid/--iam-code")
        return 2

    if args.show_token or args.only_token:
        print(token)

    if args.only_token:
        return 0

    payload: dict[str, Any] = {"pageNum": args.page_num, "pageSize": args.page_size}
    payload.update(extra)

    try:
        result = request_project_list(token=token, payload=payload, timeout=args.timeout)
    except Exception as exc:
        print(f"project list request failed: {exc}")
        return 1

    print(f"code={result.get('code')}, message={result.get('message')}")
    data = result.get("data")
    projects = find_project_list(data)
    if projects is None:
        print("Cannot find project list in response data.")
        if isinstance(data, dict):
            print("data keys:", ", ".join(data.keys()))
    else:
        print(f"Project count in current page: {len(projects)}")
        print(json.dumps(projects, ensure_ascii=False, indent=2))

    if args.show_raw:
        print("\nRaw response:")
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
