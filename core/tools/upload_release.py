"""Upload release assets to GitHub and Gitee Releases.

Tokens come only from the environment:

- ``GITHUB_TOKEN`` with ``repo`` scope.
- ``GITEE_TOKEN`` from Gitee Settings -> Private Tokens, with ``projects``
  scope.

The script never stores a token, never reads a token file and never prompts.
A missing token is an error with instructions.

Usage::

    set GITHUB_TOKEN=...
    set GITEE_TOKEN=...
    python -I core/tools/upload_release.py --version 0.2.1 --replace
    python -I core/tools/upload_release.py --target github
    python -I core/tools/upload_release.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

_TOOL_ROOT = Path(__file__).resolve().parent.parent
if str(_TOOL_ROOT) not in sys.path:
    sys.path.insert(0, str(_TOOL_ROOT))

from lvgl_ai import paths
from tools import release_bundle

DEFAULT_GITHUB_REPO = "ZEQUAN-LIANG/lvgl-for-ai"
DEFAULT_GITEE_REPO = "liang-zequan/lvgl-for-ai"
GITHUB_API = "https://api.github.com"
GITHUB_UPLOADS = "https://uploads.github.com"
GITEE_API = "https://gitee.com/api/v5"
USER_AGENT = "lvgl-verify-loop-release"


class UploadError(Exception):
    pass


SUMMARY_SCHEMA = release_bundle.BUNDLE_SCHEMA
BUNDLE_KEYS = ("full", "full_sifli")


def _manifest_assets(
    assets_dir: Path, manifest_path: Path, version: str
) -> list[Path]:
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise UploadError(f"cannot read {manifest_path}: {exc}") from exc
    if (
        not isinstance(payload, dict)
        or payload.get("schema") != SUMMARY_SCHEMA
    ):
        raise UploadError(
            f"{manifest_path}: schema must be {SUMMARY_SCHEMA!r}"
        )
    if payload.get("tool_version") != version:
        raise UploadError(
            f"{manifest_path}: tool_version must be {version!r}, "
            f"found {payload.get('tool_version')!r}"
        )
    zips: list[Path] = []
    checksums: list[Path] = []
    for key in BUNDLE_KEYS:
        record = payload.get(key)
        if not isinstance(record, dict):
            raise UploadError(f"{manifest_path}: {key} must be an object")
        zip_value = record.get("zip")
        if not isinstance(zip_value, str) or not zip_value:
            raise UploadError(f"{manifest_path}: {key}.zip must be a string")
        zip_path = assets_dir / Path(zip_value).name
        checksum = assets_dir / (zip_path.name + ".sha256")
        if not zip_path.is_file():
            raise UploadError(f"declared zip is missing: {zip_path}")
        if not checksum.is_file():
            raise UploadError(f"declared checksum is missing: {checksum}")
        zips.append(zip_path)
        checksums.append(checksum)
    return zips + checksums + [manifest_path]


def release_assets(assets_dir: Path, version: str) -> list[Path]:
    if not re.fullmatch(r"[0-9A-Za-z._-]+", version):
        raise UploadError(f"invalid release version: {version!r}")
    manifest_path = assets_dir / "release.json"
    if manifest_path.is_file():
        return _manifest_assets(assets_dir, manifest_path, version)
    zips = [
        path
        for path in assets_dir.glob(f"lvgl-verify-loop-{version}-*.zip")
        if path.is_file()
    ]
    checksums = [
        path
        for path in assets_dir.glob(f"lvgl-verify-loop-{version}-*.sha256")
        if path.is_file()
    ]
    if not zips:
        raise UploadError(
            f"no lvgl-verify-loop-{version}-*.zip assets found in {assets_dir}"
        )
    return sorted(zips) + sorted(checksums)


def resolve_token(env_name: str, provider: str) -> str:
    token = os.environ.get(env_name, "").strip()
    if token:
        return token
    raise UploadError(
        f"{env_name} is not set. Set it in the environment before running "
        f"this script; create a {provider} token with release permissions. "
        "The script does not read token files or prompt for tokens."
    )


def load_notes(assets_dir: Path, notes_file: Path | None) -> str | None:
    path = notes_file or (assets_dir / "RELEASE_NOTES.md")
    if not path.is_file():
        if notes_file is not None:
            raise UploadError(f"release notes file was not found: {path}")
        return None
    return path.read_text(encoding="utf-8")


def log(message: str) -> None:
    print(message, file=sys.stderr)


def redact(text: str, token: str) -> str:
    return text.replace(token, "***") if token else text


class UrllibTransport:
    def request(
        self,
        method: str,
        url: str,
        *,
        token: str,
        bearer: bool = False,
        data: bytes | None = None,
        content_type: str | None = None,
        allow_404: bool = False,
    ) -> tuple[int, Any]:
        headers = {"User-Agent": USER_AGENT}
        if content_type:
            headers["Content-Type"] = content_type
        if bearer:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(
            url, data=data, headers=headers, method=method
        )
        try:
            with urllib.request.urlopen(req, timeout=300) as response:
                body = response.read()
                return response.status, (
                    json.loads(body.decode("utf-8")) if body else None
                )
        except urllib.error.HTTPError as exc:
            body = redact(exc.read().decode("utf-8", "replace"), token)
            if allow_404 and exc.code == 404:
                return 404, None
            raise UploadError(
                f"{method} {url.split('?', 1)[0]} -> {exc.code}: {body[:500]}"
            ) from exc


DEFAULT_TRANSPORT = UrllibTransport()


def request(
    method: str,
    url: str,
    *,
    token: str,
    bearer: bool = False,
    data: bytes | None = None,
    content_type: str | None = None,
    allow_404: bool = False,
) -> tuple[int, Any]:
    return DEFAULT_TRANSPORT.request(
        method,
        url,
        token=token,
        bearer=bearer,
        data=data,
        content_type=content_type,
        allow_404=allow_404,
    )


def multipart(filename: str, data: bytes, token: str) -> tuple[bytes, str]:
    boundary = "----lvgl-verify-loop-" + uuid.uuid4().hex
    safe_name = filename.replace('"', "")
    chunks = [
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="access_token"\r\n\r\n'
        f"{token}\r\n".encode("utf-8"),
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{safe_name}"\r\n'
        "Content-Type: application/zip\r\n\r\n".encode("utf-8"),
        data,
        b"\r\n",
        f"--{boundary}--\r\n".encode("utf-8"),
    ]
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _gitee_url(
    repo: str, path: str, token: str, api_base: str = GITEE_API
) -> str:
    separator = "&" if "?" in path else "?"
    return (
        f"{api_base}/repos/{repo}{path}"
        f"{separator}access_token={urllib.parse.quote(token)}"
    )


def _gitee_request(
    method: str,
    repo: str,
    path: str,
    token: str,
    *,
    data: bytes | None = None,
    content_type: str | None = None,
    allow_404: bool = False,
    api_base: str = GITEE_API,
    transport: Any = None,
) -> tuple[int, Any]:
    client = transport or DEFAULT_TRANSPORT
    return client.request(
        method,
        _gitee_url(repo, path, token, api_base),
        token=token,
        data=data,
        content_type=content_type,
        allow_404=allow_404,
    )


def upload_github(
    *,
    repo: str,
    tag: str,
    version: str,
    notes: str | None,
    assets: list[Path],
    token: str,
    replace: bool,
    dry_run: bool,
    api_base: str = GITHUB_API,
    uploads_base: str = GITHUB_UPLOADS,
    transport: Any = None,
) -> str:
    client = transport or DEFAULT_TRANSPORT
    base = f"{api_base}/repos/{repo}"
    url = f"https://github.com/{repo}/releases/tag/{tag}"
    if dry_run:
        log(f"[github] would upload {len(assets)} assets to {tag}")
        return url
    status, release = client.request(
        "GET",
        f"{base}/releases/tags/{tag}",
        token=token,
        bearer=True,
        allow_404=True,
    )
    name = f"LVGL Verify Loop {version}"
    if status == 404:
        _status, release = client.request(
            "POST",
            f"{base}/releases",
            token=token,
            bearer=True,
            data=json.dumps(
                {
                    "tag_name": tag,
                    "name": name,
                    "body": notes or name,
                    "draft": False,
                    "prerelease": False,
                }
            ).encode("utf-8"),
            content_type="application/json",
        )
    else:
        if not isinstance(release, dict) or not release.get("id"):
            raise UploadError("GitHub did not return a release with an id")
        patch: dict[str, Any] = {"name": name}
        if notes is not None:
            patch["body"] = notes
        client.request(
            "PATCH",
            f"{base}/releases/{release['id']}",
            token=token,
            bearer=True,
            data=json.dumps(patch).encode("utf-8"),
            content_type="application/json",
        )
    if not isinstance(release, dict) or not release.get("id"):
        raise UploadError("GitHub did not return a release with an id")
    release_id = release["id"]
    existing = {
        asset["name"]: asset["id"] for asset in (release.get("assets") or [])
    }
    for path in assets:
        if path.name in existing:
            if not replace:
                log(f"[github] exists {path.name}")
                continue
            client.request(
                "DELETE",
                f"{base}/releases/assets/{existing[path.name]}",
                token=token,
                bearer=True,
                allow_404=True,
            )
            log(f"[github] deleted old {path.name}")
        status, asset = client.request(
            "POST",
            f"{uploads_base}/repos/{repo}/releases/{release_id}/assets"
            f"?name={urllib.parse.quote(path.name)}",
            token=token,
            bearer=True,
            data=path.read_bytes(),
            content_type="application/zip",
        )
        size = (asset or {}).get("size", "")
        log(f"[github] {status} {path.name} {size}".rstrip())
    return release.get("html_url", url)


def upload_gitee(
    *,
    repo: str,
    tag: str,
    version: str,
    notes: str | None,
    target_commitish: str | None,
    assets: list[Path],
    token: str,
    replace: bool,
    dry_run: bool,
    api_base: str = GITEE_API,
    transport: Any = None,
) -> str:
    client = transport or DEFAULT_TRANSPORT
    page = f"https://gitee.com/{repo}/releases/tag/{tag}"
    if dry_run:
        log(f"[gitee] would upload {len(assets)} assets to {tag}")
        return page

    def gitee(
        method: str,
        path: str,
        *,
        data: bytes | None = None,
        content_type: str | None = None,
        allow_404: bool = False,
    ) -> tuple[int, Any]:
        return _gitee_request(
            method,
            repo,
            path,
            token,
            data=data,
            content_type=content_type,
            allow_404=allow_404,
            api_base=api_base,
            transport=client,
        )

    _status, release = gitee("GET", f"/releases/tags/{tag}", allow_404=True)
    name = f"LVGL Verify Loop {version}"
    if not isinstance(release, dict):
        form = urllib.parse.urlencode(
            {
                "tag_name": tag,
                "name": name,
                "body": notes or name,
                "target_commitish": target_commitish or "dev",
                "prerelease": "false",
            }
        ).encode("utf-8")
        _status, release = gitee(
            "POST",
            "/releases",
            data=form,
            content_type="application/x-www-form-urlencoded",
        )
    else:
        if not release.get("id"):
            raise UploadError("Gitee did not return a release with an id")
        # Gitee requires ``body`` on PATCH. When no notes file was given,
        body = notes if notes is not None else release.get("body")
        patch = {
            "tag_name": tag,
            "name": name,
            "body": body if isinstance(body, str) else "",
        }
        if target_commitish:
            patch["target_commitish"] = target_commitish
        form = urllib.parse.urlencode(patch).encode("utf-8")
        gitee(
            "PATCH",
            f"/releases/{release['id']}",
            data=form,
            content_type="application/x-www-form-urlencoded",
        )
    if not isinstance(release, dict) or not release.get("id"):
        raise UploadError("Gitee did not return a release with an id")
    release_id = release["id"]
    _status, attachments = gitee("GET", f"/releases/{release_id}/attach_files")
    existing = {
        item["name"]: item["id"]
        for item in (attachments or [])
        if isinstance(item, dict) and item.get("name") and item.get("id")
    }
    for path in assets:
        if path.name in existing:
            if not replace:
                log(f"[gitee] exists {path.name}")
                continue
            gitee(
                "DELETE",
                f"/releases/{release_id}/attach_files/{existing[path.name]}",
                allow_404=True,
            )
            log(f"[gitee] deleted old {path.name}")
        body, content_type = multipart(path.name, path.read_bytes(), token)
        _status, _ = gitee(
            "POST",
            f"/releases/{release_id}/attach_files",
            data=body,
            content_type=content_type,
        )
        log(f"[gitee] {_status} {path.name}")
    return page


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="upload_release.py",
        description="Upload release assets to GitHub and Gitee Releases.",
    )
    parser.add_argument("--version", default=paths.TOOL_VERSION)
    parser.add_argument("--tag", default=None, help="default: v<version>")
    parser.add_argument(
        "--assets-dir", type=Path, default=None, help="default: <repo>/release"
    )
    parser.add_argument(
        "--target", choices=("all", "github", "gitee"), default="all"
    )
    parser.add_argument(
        "--replace",
        action="store_true",
        help="delete an existing asset with the same name before uploading",
    )
    parser.add_argument(
        "--notes-file",
        type=Path,
        default=None,
        help="default: <assets-dir>/RELEASE_NOTES.md; otherwise keep the body",
    )
    parser.add_argument(
        "--target-commitish",
        default=None,
        help="Gitee target commit; default: keep it, or dev for a new release",
    )
    parser.add_argument("--github-repo", default=DEFAULT_GITHUB_REPO)
    parser.add_argument("--gitee-repo", default=DEFAULT_GITEE_REPO)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    assets_dir = (args.assets_dir or (paths.REPO_ROOT / "release")).resolve()
    tag = args.tag or f"v{args.version}"
    try:
        assets = release_assets(assets_dir, args.version)
        notes = load_notes(assets_dir, args.notes_file)
        summary: dict[str, Any] = {
            "version": args.version,
            "tag": tag,
            "assets": [path.name for path in assets],
        }
        if args.target in ("all", "github"):
            token = (
                "" if args.dry_run else resolve_token("GITHUB_TOKEN", "GitHub")
            )
            summary["github"] = upload_github(
                repo=args.github_repo,
                tag=tag,
                version=args.version,
                notes=notes,
                assets=assets,
                token=token,
                replace=args.replace,
                dry_run=args.dry_run,
            )
        if args.target in ("all", "gitee"):
            token = (
                "" if args.dry_run else resolve_token("GITEE_TOKEN", "Gitee")
            )
            summary["gitee"] = upload_gitee(
                repo=args.gitee_repo,
                tag=tag,
                version=args.version,
                notes=notes,
                target_commitish=args.target_commitish,
                assets=assets,
                token=token,
                replace=args.replace,
                dry_run=args.dry_run,
            )
    except (UploadError, OSError, ValueError) as exc:
        print(f"[upload_release] {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(summary, ensure_ascii=False))
    else:
        if "github" in summary:
            print(f"GitHub: {summary['github']}")
        if "gitee" in summary:
            print(f"Gitee:  {summary['gitee']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
