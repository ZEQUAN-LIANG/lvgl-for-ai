"""Fetch pinned zlib and libpng source trees into ``third_party/``.

The engine writes PNG evidence with libpng + zlib, not LVGL's bundled
lodepng.  Both trees are pinned by tag and commit, and are cloned into
``.scratch/tmp`` before being copied to ``third_party/<name>/``.  The
downloaded trees are untrusted data: this script only reads them and never
builds or executes them.  Builds happen from ``third_party/``.

Run with ``python -I`` and an explicit repository root:

    python -I core/tools/fetch_png.py --repo-root .
    python -I core/tools/fetch_png.py --repo-root . --force
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

ZLIB = {
    "name": "zlib",
    "version": "1.3.1",
    "tag": "v1.3.1",
    # Commit pointed to by the annotated v1.3.1 tag.
    "commit": "51b7f2abdade71cd9bb0e7a373ef2610ec6f9daf",
    "url": "https://github.com/madler/zlib.git",
    "header": "zlib.h",
    "macro": "ZLIB_VERSION",
}

LIBPNG = {
    "name": "libpng",
    "version": "1.6.44",
    "tag": "v1.6.44",
    # Commit pointed to by the annotated v1.6.44 tag.
    "commit": "f5e92d76973a7a53f517579bc95d61483bf108c0",
    "url": "https://github.com/pnggroup/libpng.git",
    "header": "png.h",
    "macro": "PNG_LIBPNG_VER_STRING",
}


def clone(spec: dict[str, str], work: Path) -> None:
    command = [
        "git",
        "clone",
        "--depth",
        "1",
        "--branch",
        spec["tag"],
        spec["url"],
        str(work),
    ]
    for attempt in range(3):
        if work.exists():
            shutil.rmtree(work)
        try:
            subprocess.run(command, check=True)
            return
        except FileNotFoundError:
            raise SystemExit(
                "git is required to fetch the pinned zlib/libpng trees"
            )
        except subprocess.CalledProcessError as exc:
            if attempt == 2:
                raise SystemExit(
                    f"command failed ({exc.returncode}): {' '.join(command)}"
                )
            print(
                f"clone failed (attempt {attempt + 1}/3); retrying",
                flush=True,
            )
            time.sleep(2)


def source_matches(tree: Path, spec: dict[str, str]) -> bool:
    header = tree / spec["header"]
    if not header.is_file():
        return False
    text = header.read_text(encoding="utf-8", errors="replace")
    pattern = rf'^#define\s+{spec["macro"]}\s+"{re.escape(spec["version"])}"'
    return re.search(pattern, text, re.MULTILINE) is not None


def install(repo_root: Path, spec: dict[str, str], *, force: bool) -> None:
    destination = repo_root / "third_party" / spec["name"]
    if not force and source_matches(destination, spec):
        print(f"{spec['name']} {spec['version']} already installed")
        return

    work = (
        repo_root
        / ".scratch"
        / "tmp"
        / "png-src"
        / f"{spec['name']}-{spec['version']}"
    )
    work.parent.mkdir(parents=True, exist_ok=True)
    if work.exists():
        shutil.rmtree(work)

    print(f"clone {spec['url']} {spec['tag']}", flush=True)
    clone(spec, work)
    head = subprocess.check_output(
        ["git", "-C", str(work), "rev-parse", "HEAD"],
        text=True,
    ).strip()
    if head != spec["commit"]:
        raise SystemExit(
            f"{spec['name']}: tag {spec['tag']} is {head}, expected {spec['commit']}"
        )
    if not source_matches(work, spec):
        raise SystemExit(
            f"{spec['name']}: {spec['header']} is not version {spec['version']}"
        )

    staging = destination.with_name(destination.name + ".tmp")
    if staging.exists():
        shutil.rmtree(staging)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        work, staging, ignore=shutil.ignore_patterns(".git")
    )
    if destination.exists():
        shutil.rmtree(destination)
    staging.replace(destination)
    print(
        f"installed {spec['name']} {spec['version']} at {destination}",
        flush=True,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument(
        "--force",
        action="store_true",
        help="reinstall even when the pinned version is already present",
    )
    args = parser.parse_args()

    repo_root = args.repo_root.expanduser().resolve()
    if not (repo_root / "core").is_dir():
        raise SystemExit(f"{repo_root}: core/ not found")
    install(repo_root, ZLIB, force=args.force)
    install(repo_root, LIBPNG, force=args.force)
    return 0


if __name__ == "__main__":
    sys.exit(main())
