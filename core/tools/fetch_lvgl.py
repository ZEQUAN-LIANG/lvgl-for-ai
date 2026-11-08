"""Fetch official LVGL release tarballs and install them into lvgl-src/.

This script fetches the official tags for 9.6 / 9.5 / 9.4 / 9.1 / 8.4 / 8.3.
Every archive is installed only after its version macros match the requested
version.  Local changes are applied from ``patches/<version>/`` as unified
diffs before the tree is installed.

Run with ``python -I`` and absolute paths.  Downloaded archives and extracted
trees are untrusted data: they live in their own directories under
``.scratch/tmp`` and are only read by this script, which never executes
anything from them.

Usage:
    python -I core/tools/fetch_lvgl.py --version 9.5 --repo-root .
    python -I core/tools/fetch_lvgl.py --version 8.3 --source gitee
    python -I core/tools/fetch_lvgl.py --version 9.6 --repo-root . --no-patch
    python -I core/tools/fetch_lvgl.py --version 9.6 --repo-root . --patch-dir my-patches
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

TAGS = {
    "8.4": "v8.4.0",
    "8.3": "v8.3.11",
    "9.6": "v9.6.0",
    "9.5": "v9.5.0",
    "9.4": "v9.4.0",
    "9.1": "v9.1.0",
}

SOURCE_SCHEMA = "lvgl-ai-lvgl-source-v1"

# github.com resolves to a parked domain in some networks; codeload and the
# Gitee mirror both serve the same official tag archives.  When DNS is
# poisoned, codeload is retried with --resolve against well-known GitHub IPs.
CODELOAD_URL = "https://codeload.github.com/lvgl/lvgl/tar.gz/refs/tags/{tag}"
GITEE_URL = "https://gitee.com/mirrors/lvgl/repository/archive/{tag}.tar.gz"
GITHUB_IPS = ("140.82.112.9", "140.82.113.9", "140.82.114.9")


def parse_version_header(tree: Path) -> tuple[int, int, int]:
    candidates = (
        tree / "include" / "lvgl" / "lv_version.h",
        tree / "lv_version.h",
        # LVGL 9.1 and older define the version macros in the root lvgl.h.
        tree / "lvgl.h",
    )
    path = next((item for item in candidates if item.is_file()), None)
    if path is None:
        raise SystemExit(f"{tree}: version header (lv_version.h or lvgl.h) not found")
    text = path.read_text(encoding="utf-8", errors="replace")
    values = {}
    for name in ("LVGL_VERSION_MAJOR", "LVGL_VERSION_MINOR", "LVGL_VERSION_PATCH"):
        match = re.search(rf"^#define\s+{name}\s+(\d+)\s*$", text, re.MULTILINE)
        if match is None:
            raise SystemExit(f"{path}: missing {name}")
        values[name] = int(match.group(1))
    return (
        values["LVGL_VERSION_MAJOR"],
        values["LVGL_VERSION_MINOR"],
        values["LVGL_VERSION_PATCH"],
    )


def _curl(url: str, archive: Path, *, resolve_ip: str | None) -> int:
    command = [
        "curl",
        "-L",
        "--fail",
        "--silent",
        "--show-error",
        "--retry",
        "2",
        "--connect-timeout",
        "10",
        "--max-time",
        "600",
        "-o",
        str(archive),
    ]
    if resolve_ip is not None:
        command.extend(["--resolve", f"codeload.github.com:443:{resolve_ip}"])
    command.append(url)
    return subprocess.run(command).returncode


def download(tag: str, archive: Path, source: str) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    if archive.is_file() and archive.stat().st_size > 0:
        try:
            with tarfile.open(archive, "r:gz") as tar:
                tar.getmembers()
        except tarfile.TarError:
            archive.unlink()
        else:
            print(f"reusing downloaded archive {archive}", flush=True)
            return
    errors = []
    attempts = []
    if source in ("auto", "codeload"):
        attempts.append((CODELOAD_URL.format(tag=tag), None))
        attempts += [(CODELOAD_URL.format(tag=tag), ip) for ip in GITHUB_IPS]
    if source in ("auto", "gitee"):
        attempts.append((GITEE_URL.format(tag=tag), None))
    for url, resolve_ip in attempts:
        label = f"{url} (resolve {resolve_ip})" if resolve_ip else url
        print(f"download {label}", flush=True)
        returncode = _curl(url, archive, resolve_ip=resolve_ip)
        if returncode == 0 and archive.is_file() and archive.stat().st_size > 0:
            print(f"downloaded {archive.stat().st_size} bytes", flush=True)
            return
        errors.append(f"{label}: curl exit {returncode}")
        archive.unlink(missing_ok=True)
    raise SystemExit("all download URLs failed:\n" + "\n".join(errors))


def extract(archive: Path, extract_root: Path) -> Path:
    if extract_root.exists():
        shutil.rmtree(extract_root)
    extract_root.mkdir(parents=True)
    with tarfile.open(archive, "r:gz") as tar:
        root = tar.getmembers()[0].name.split("/")[0]
        for member in tar.getmembers():
            # Reject absolute or parent-traversing members before writing.
            if member.issym() or member.islnk():
                raise SystemExit(f"unsafe archive member: {member.name}")
            target = (extract_root / member.name).resolve()
            if extract_root.resolve() not in target.parents and target != extract_root.resolve():
                raise SystemExit(f"unsafe archive member: {member.name}")
        try:
            tar.extractall(extract_root, filter="data")
        except TypeError:
            # Python < 3.12 has no extraction filters; the member check above
            # already rejects absolute and parent-traversing names.
            tar.extractall(extract_root)
    tree = extract_root / root
    if not tree.is_dir():
        raise SystemExit(f"unexpected archive layout: {root}")
    return tree


def verify_tree(tree: Path, version: str) -> tuple[int, int, int]:
    actual = parse_version_header(tree)
    # The tag is the release identity, including patch-level tags such as
    # v8.3.11; the version macros must name exactly that release.
    tag = TAGS[version]
    expected = tuple(int(part) for part in tag.lstrip("v").split("."))
    if actual != expected:
        raise SystemExit(
            f"version header mismatch: tag {tag} expects {expected}, "
            f"header says {actual[0]}.{actual[1]}.{actual[2]}"
        )
    if not (
        (tree / "include" / "lvgl" / "lvgl.h").is_file()
        or (tree / "lvgl.h").is_file()
    ):
        raise SystemExit(f"missing lvgl.h in {tree}")
    return actual


def install(tree: Path, dest: Path, version: str) -> None:
    actual = verify_tree(tree, version)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(tree, dest)
    print(f"installed LVGL {actual[0]}.{actual[1]}.{actual[2]} -> {dest}", flush=True)


def patch_dir_for(repo_root: Path, version: str, override: Path | None) -> Path:
    base = override if override is not None else repo_root / "patches"
    return base / version


def _read_series(series: Path) -> list[str]:
    names = []
    for lineno, raw in enumerate(series.read_text(encoding="utf-8").splitlines(), 1):
        entry = raw.strip()
        if not entry or entry.startswith("#"):
            continue
        candidate = Path(entry)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise SystemExit(f"{series}:{lineno}: unsafe patch path: {entry!r}")
        if candidate.suffix != ".patch":
            raise SystemExit(f"{series}:{lineno}: expected a .patch file: {entry!r}")
        names.append(entry)
    return names


def discover_patches(patch_dir: Path) -> list[Path]:
    """Return the patches to apply, in order.

    ``series`` is authoritative when present.  Without it, every ``*.patch`` in
    the version directory is applied in lexical order.
    """
    if not patch_dir.is_dir():
        return []
    series = patch_dir / "series"
    if series.is_file():
        names = _read_series(series)
    else:
        names = [path.name for path in sorted(patch_dir.glob("*.patch"))]
    patches = []
    for name in names:
        path = patch_dir / name
        if not path.is_file():
            raise SystemExit(f"patch not found: {path}")
        patches.append(path)
    return patches


def _git_apply(tree: Path, patch: Path, *, check: bool) -> None:
    command = ["git", "apply", "--whitespace=nowarn"]
    if check:
        command.append("--check")
    command.append(str(patch))
    try:
        result = subprocess.run(
            command,
            cwd=tree,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        raise SystemExit("git is required to apply LVGL patches")
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        action = "check" if check else "apply"
        raise SystemExit(f"git apply --{action} failed for {patch}:\n{detail}")


def apply_patches(tree: Path, patches: list[Path]) -> None:
    for patch in patches:
        _git_apply(tree, patch, check=True)
        _git_apply(tree, patch, check=False)
        print(f"applied patch {patch.name}", flush=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_source_stamp(dest: Path, version: str, patches: list[Path]) -> None:
    payload = {
        "schema": SOURCE_SCHEMA,
        "version": version,
        "tag": TAGS[version],
        "patches": [patch.name for patch in patches],
        "patch_sha256": {patch.name: _sha256(patch) for patch in patches},
    }
    path = dest / ".lvgl-ai-source.json"
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {path}", flush=True)


def source_stamp_matches(dest: Path, version: str, patches: list[Path]) -> bool:
    stamp = dest / ".lvgl-ai-source.json"
    if not stamp.is_file():
        return False
    try:
        payload = json.loads(stamp.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return (
        payload.get("schema") == SOURCE_SCHEMA
        and payload.get("version") == version
        and payload.get("tag") == TAGS[version]
        and payload.get("patches") == [patch.name for patch in patches]
        and payload.get("patch_sha256")
        == {patch.name: _sha256(patch) for patch in patches}
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--version", required=True, choices=sorted(TAGS))
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--source", choices=("auto", "codeload", "gitee"), default="auto")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--patch-dir",
        type=Path,
        default=None,
        help="patch root; <version> is appended (default: <repo-root>/patches)",
    )
    parser.add_argument(
        "--no-patch",
        action="store_true",
        help="install the official tree without local patches",
    )
    args = parser.parse_args()

    version = args.version
    tag = TAGS[version]
    repo_root = args.repo_root.resolve()
    dest = repo_root / "lvgl-src" / version
    patch_dir = patch_dir_for(
        repo_root,
        version,
        args.patch_dir.resolve() if args.patch_dir is not None else None,
    )
    patches = [] if args.no_patch else discover_patches(patch_dir)

    if dest.is_dir() and not args.force:
        actual = parse_version_header(dest)
        if patches and not source_stamp_matches(dest, version, patches):
            raise SystemExit(
                f"{dest} exists but does not match the patches for LVGL {version}; "
                "rerun with --force to replace it"
            )
        print(f"already installed: {dest} (LVGL {actual[0]}.{actual[1]}.{actual[2]})")
        return 0

    if patches:
        print(f"applying {len(patches)} patch(es) from {patch_dir}", flush=True)
    elif patch_dir.is_dir():
        print(f"no patches in {patch_dir}", flush=True)

    archive = repo_root / ".scratch" / "tmp" / "archives" / f"lvgl-{tag}.tar.gz"
    extract_root = repo_root / ".scratch" / "tmp" / "downloads" / version
    download(tag, archive, args.source)
    tree = extract(archive, extract_root)
    verify_tree(tree, version)
    apply_patches(tree, patches)
    install(tree, dest, version)
    write_source_stamp(dest, version, patches)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
