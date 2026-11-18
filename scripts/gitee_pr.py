#!/usr/bin/env python3
"""Create, update and verify Gitee pull requests from UTF-8 files.

The Windows shell can silently re-encode inline Chinese arguments (GBK/ANSI),
which is how a PR body turns into replacement characters.  This helper never sends text from
the command line: titles and bodies come from UTF-8 files, are encoded as
UTF-8 explicitly, and the stored PR is read back and verified.

Examples::

    python -I scripts/gitee_pr.py create \\
        --head feat/esp32-ble-dual --base dev \\
        --title-file .tmp/title.txt --body-file .tmp/body.md --json

    python -I scripts/gitee_pr.py update 24 --body-file .tmp/body.md --json

    python -I scripts/gitee_pr.py show 24 --json

    python -I scripts/gitee_pr.py verify 24 \\
        --title-file .tmp/title.txt --body-file .tmp/body.md --json

``GITEE_TOKEN`` must be set in the environment; the token is never accepted on
the command line and never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Optional

DEFAULT_API_BASE = "https://gitee.com/api/v5"
DEFAULT_BASE_BRANCH = "dev"
DEFAULT_TIMEOUT = 30.0
_GITEE_REMOTE_RE = re.compile(
    r"gitee\.com[:/](?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$"
)


class CliError(RuntimeError):
    def __init__(self, message: str, *, code: str = "error") -> None:
        super().__init__(message)
        self.code = code


def _read_utf8_file(path: str, label: str) -> str:
    file_path = Path(path)
    if not file_path.is_file():
        raise CliError(f"{label} file not found: {path}", code="file_missing")
    try:
        raw = file_path.read_bytes()
    except OSError as exc:
        raise CliError(
            f"cannot read {label} file {path}: {exc}", code="file_read_failed"
        ) from exc
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise CliError(
            f"{label} file is not valid UTF-8: {path}: {exc}",
            code="file_not_utf8",
        ) from exc
    if "\x00" in text:
        raise CliError(
            f"{label} file contains NUL bytes: {path}", code="file_not_text"
        )
    return text


def _resolve_text(
    *,
    inline: Optional[str],
    file_path: Optional[str],
    label: str,
    required: bool,
) -> str:
    if file_path:
        text = _read_utf8_file(file_path, label)
    elif inline is not None:
        text = inline
    else:
        text = ""
    if required and not text.strip():
        raise CliError(
            f"{label} is empty; pass --{label}-file or --{label}",
            code=f"{label}_missing",
        )
    return text


def _run_git(args: list[str]) -> str:
    try:
        completed = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise CliError(f"git failed: {exc}", code="git_error") from exc
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise CliError(
            f"git {' '.join(args)} failed: {detail}", code="git_error"
        )
    return completed.stdout.strip()


def infer_repo() -> str:
    remote = _run_git(["remote", "get-url", "origin"])
    match = _GITEE_REMOTE_RE.search(remote)
    if not match:
        raise CliError(
            "cannot infer a Gitee repo from origin; pass --repo OWNER/REPO",
            code="repo_missing",
        )
    return f"{match.group('owner')}/{match.group('repo')}"


def current_branch() -> str:
    return _run_git(["branch", "--show-current"])


def _validate_repo(repo: str) -> str:
    value = repo.strip().strip("/")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value):
        raise CliError(
            f"invalid repo {repo!r}; expected OWNER/REPO", code="repo_invalid"
        )
    return value


def _token() -> str:
    token = str(os.environ.get("GITEE_TOKEN") or "").strip()
    if not token:
        raise CliError(
            "GITEE_TOKEN is not set in the environment", code="token_missing"
        )
    return token


def _redact(text: str, token: str) -> str:
    return text.replace(token, "***") if token else text


def _api_url(api_base: str, repo: str, suffix: str) -> str:
    return f"{api_base.rstrip('/')}/repos/{repo}/pulls{suffix}"


def _request(
    *,
    method: str,
    url: str,
    token: str,
    payload: Optional[dict[str, str]] = None,
    timeout: float = DEFAULT_TIMEOUT,
) -> dict[str, Any]:
    data: Optional[bytes] = None
    headers = {
        "Accept": "application/json",
        "User-Agent": "lvgl-for-ai-gitee-pr/1",
    }
    if method == "GET":
        query = urllib.parse.urlencode({"access_token": token})
        target = f"{url}{'&' if '?' in url else '?'}{query}"
    else:
        form = dict(payload or {})
        form["access_token"] = token
        data = urllib.parse.urlencode(form).encode("utf-8")
        headers["Content-Type"] = (
            "application/x-www-form-urlencoded; charset=utf-8"
        )
        target = url
    request = urllib.request.Request(
        target, data=data, method=method, headers=headers
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read()
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", "replace")
        except Exception:
            pass
        detail = body.strip()[:800]
        raise CliError(
            _redact(
                f"Gitee API {method} {url} failed: HTTP {exc.code} {detail}",
                token,
            ),
            code="api_http_error",
        ) from exc
    except urllib.error.URLError as exc:
        raise CliError(
            _redact(f"Gitee API unreachable: {exc.reason}", token),
            code="api_unreachable",
        ) from exc
    except TimeoutError as exc:
        raise CliError(
            _redact(f"Gitee API timed out after {timeout}s", token),
            code="api_timeout",
        ) from exc
    try:
        result = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise CliError(
            "Gitee API returned invalid JSON", code="api_bad_json"
        ) from exc
    if not isinstance(result, dict):
        raise CliError(
            "Gitee API returned a non-object payload", code="api_bad_json"
        )
    return result


def _normalize(text: str) -> str:
    """Ignore Gitee's emoji stripping and whitespace-only differences."""

    value = text.replace("\r\n", "\n")
    value = "".join(ch for ch in value if ord(ch) < 0x1F000)
    value = re.sub(r"[ \t]+", " ", value)
    return value.strip()


def _first_difference(expected: str, actual: str) -> Optional[int]:
    left = expected.replace("\r\n", "\n")
    right = actual.replace("\r\n", "\n")
    for index, (expected_ch, actual_ch) in enumerate(zip(left, right)):
        if expected_ch != actual_ch:
            return index
    if len(left) != len(right):
        return min(len(left), len(right))
    return None


def _verify_body(
    stored: dict[str, Any],
    *,
    title: Optional[str],
    body: Optional[str],
) -> dict[str, Any]:
    stored_title = str(stored.get("title") or "")
    stored_body = str(stored.get("body") or "")
    issues: list[str] = []
    if title is not None and stored_title.strip() != title.strip():
        issues.append("title_mismatch")
    exact = True
    if body is not None:
        exact = (
            stored_body.replace("\r\n", "\n").rstrip()
            == body.replace("\r\n", "\n").rstrip()
        )
        if not exact and _normalize(stored_body) != _normalize(body):
            issues.append("body_mismatch")
    replacement_chars = stored_body.count("\ufffd")
    if replacement_chars:
        issues.append("replacement_chars")
    return {
        "verified": not issues,
        "exact": exact,
        "replacement_chars": replacement_chars,
        "first_difference": (
            _first_difference(body, stored_body)
            if body is not None and not exact
            else None
        ),
        "issues": issues,
    }


def _summary(
    *,
    action: str,
    result: dict[str, Any],
    verification: dict[str, Any],
) -> dict[str, Any]:
    return {
        "ok": not verification.get("issues"),
        "action": action,
        "number": result.get("number"),
        "state": result.get("state"),
        "title": result.get("title"),
        "html_url": result.get("html_url"),
        "head": (result.get("head") or {}).get("ref"),
        "base": (result.get("base") or {}).get("ref"),
        **verification,
    }


def _print(payload: dict[str, Any], *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, ensure_ascii=False))
        return
    if payload.get("dry_run"):
        print(f"dry-run {payload.get('method')} {payload.get('url')}")
        print(
            json.dumps(
                payload.get("payload") or {},
                ensure_ascii=False,
                indent=2,
            )
        )
        return
    print(f"PR #{payload.get('number')} {payload.get('state')}")
    if payload.get("html_url"):
        print(f"url: {payload['html_url']}")
    if payload.get("title"):
        print(f"title: {payload['title']}")
    if payload.get("head"):
        print(f"branch: {payload['head']} -> {payload.get('base')}")
    print(
        "verified: "
        f"{payload.get('verified')} "
        f"(exact={payload.get('exact')}, "
        f"replacement_chars={payload.get('replacement_chars')})"
    )
    issues = payload.get("issues") or []
    if issues:
        print("issues: " + ", ".join(str(item) for item in issues))
    if payload.get("first_difference") is not None:
        print(f"first_difference: {payload['first_difference']}")


def cmd_create(args: argparse.Namespace) -> dict[str, Any]:
    repo = _validate_repo(args.repo or infer_repo())
    token = _token()
    head = args.head or current_branch()
    if not head:
        raise CliError(
            "detached HEAD; pass --head BRANCH", code="head_missing"
        )
    base = args.base or DEFAULT_BASE_BRANCH
    if head == base:
        raise CliError(
            f"head and base are both {base!r}; push a feature branch first",
            code="head_equals_base",
        )
    title = _resolve_text(
        inline=args.title,
        file_path=args.title_file,
        label="title",
        required=True,
    ).strip()
    body = _resolve_text(
        inline=args.body,
        file_path=args.body_file,
        label="body",
        required=False,
    )
    payload = {"title": title, "head": head, "base": base, "body": body}
    if args.dry_run:
        return {
            "ok": True,
            "action": "create",
            "dry_run": True,
            "repo": repo,
            "method": "POST",
            "url": _api_url(args.api_base, repo, ""),
            "payload": {**payload, "access_token": "***"},
        }
    result = _request(
        method="POST",
        url=_api_url(args.api_base, repo, ""),
        token=token,
        payload=payload,
        timeout=args.timeout,
    )
    verification = (
        _verify_body(result, title=title, body=body)
        if not args.no_verify
        else {"verified": None, "exact": None, "replacement_chars": None, "issues": []}
    )
    return _summary(action="create", result=result, verification=verification)


def cmd_update(args: argparse.Namespace) -> dict[str, Any]:
    repo = _validate_repo(args.repo or infer_repo())
    token = _token()
    title = (
        _resolve_text(
            inline=args.title,
            file_path=args.title_file,
            label="title",
            required=False,
        ).strip()
        if args.title is not None or args.title_file
        else None
    )
    body = (
        _resolve_text(
            inline=args.body,
            file_path=args.body_file,
            label="body",
            required=False,
        )
        if args.body is not None or args.body_file
        else None
    )
    if title is None and body is None:
        raise CliError(
            "nothing to update; pass --title-file and/or --body-file",
            code="update_empty",
        )
    payload: dict[str, str] = {}
    if title is not None:
        payload["title"] = title
    if body is not None:
        payload["body"] = body
    if args.dry_run:
        return {
            "ok": True,
            "action": "update",
            "dry_run": True,
            "repo": repo,
            "number": args.number,
            "method": "PATCH",
            "url": _api_url(args.api_base, repo, f"/{args.number}"),
            "payload": {**payload, "access_token": "***"},
        }
    result = _request(
        method="PATCH",
        url=_api_url(args.api_base, repo, f"/{args.number}"),
        token=token,
        payload=payload,
        timeout=args.timeout,
    )
    verification = (
        _verify_body(result, title=title, body=body)
        if not args.no_verify
        else {"verified": None, "exact": None, "replacement_chars": None, "issues": []}
    )
    return _summary(action="update", result=result, verification=verification)


def cmd_show(args: argparse.Namespace) -> dict[str, Any]:
    repo = _validate_repo(args.repo or infer_repo())
    token = _token()
    result = _request(
        method="GET",
        url=_api_url(args.api_base, repo, f"/{args.number}"),
        token=token,
        timeout=args.timeout,
    )
    return _summary(
        action="show",
        result=result,
        verification=_verify_body(result, title=None, body=None),
    )


def cmd_verify(args: argparse.Namespace) -> dict[str, Any]:
    repo = _validate_repo(args.repo or infer_repo())
    token = _token()
    title = _resolve_text(
        inline=args.title,
        file_path=args.title_file,
        label="title",
        required=False,
    )
    body = _resolve_text(
        inline=args.body,
        file_path=args.body_file,
        label="body",
        required=False,
    )
    if not title.strip() and not body.strip():
        raise CliError(
            "nothing to verify; pass --title-file and/or --body-file",
            code="verify_empty",
        )
    result = _request(
        method="GET",
        url=_api_url(args.api_base, repo, f"/{args.number}"),
        token=token,
        timeout=args.timeout,
    )
    verification = _verify_body(
        result,
        title=title if title.strip() else None,
        body=body if body.strip() else None,
    )
    return _summary(action="verify", result=result, verification=verification)


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--repo",
        default="",
        help="OWNER/REPO (default: inferred from git origin)",
    )
    parser.add_argument(
        "--api-base",
        default=DEFAULT_API_BASE,
        help=argparse.SUPPRESS,
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT
    )
    parser.add_argument("--dry-run", action="store_true")


def _add_text(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--title", default=None, help="inline ASCII title (prefer --title-file)"
    )
    parser.add_argument(
        "--title-file", default=None, help="UTF-8 title file"
    )
    parser.add_argument(
        "--body", default=None, help="inline ASCII body (prefer --body-file)"
    )
    parser.add_argument(
        "--body-file", default=None, help="UTF-8 Markdown body file"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create", help="create a pull request")
    _add_common(create)
    _add_text(create)
    create.add_argument("--head", default="")
    create.add_argument("--base", default=DEFAULT_BASE_BRANCH)
    create.add_argument("--no-verify", action="store_true")
    create.set_defaults(func=cmd_create)

    update = sub.add_parser("update", help="update a pull request title/body")
    _add_common(update)
    _add_text(update)
    update.add_argument("number", type=int)
    update.add_argument("--no-verify", action="store_true")
    update.set_defaults(func=cmd_update)

    show = sub.add_parser("show", help="show and inspect a pull request")
    _add_common(show)
    show.add_argument("number", type=int)
    show.set_defaults(func=cmd_show)

    verify = sub.add_parser("verify", help="verify stored title/body encoding")
    _add_common(verify)
    _add_text(verify)
    verify.add_argument("number", type=int)
    verify.set_defaults(func=cmd_verify)
    return parser


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - console encoding is best effort
            pass


def main(argv: Optional[list[str]] = None) -> int:
    _configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        payload = args.func(args)
    except CliError as exc:
        if args.json:
            print(
                json.dumps(
                    {"ok": False, "error": exc.code, "message": str(exc)},
                    ensure_ascii=False,
                )
            )
        else:
            print(f"{exc.code}: {exc}", file=sys.stderr)
        return 1
    _print(payload, as_json=args.json)
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
