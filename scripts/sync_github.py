from __future__ import annotations

import argparse
import json
import subprocess
import sys

SOURCE_REMOTE = "origin"
TARGET_REMOTE = "github"


def git(args: list[str], *, dry_run: bool = False, echo: bool = True) -> str:
    cmd = ["git", *args]
    if echo:
        print("+ " + " ".join(cmd), flush=True)
    if dry_run:
        return ""
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise SystemExit(
            f"git {' '.join(args)} failed:\n{result.stderr.strip()}"
        )
    return result.stdout


def remotes() -> set[str]:
    out = git(["remote"], echo=False)
    return set(out.split())


def list_branches(remote: str) -> list[str]:
    out = git(
        [
            "for-each-ref",
            "--format=%(refname:strip=3)",
            f"refs/remotes/{remote}/",
        ],
        echo=False,
    )
    return sorted(name for name in out.splitlines() if name and name != "HEAD")


def list_tags(remote: str) -> list[str]:
    out = git(["ls-remote", "--tags", "--refs", remote], echo=False)
    return sorted(
        line.split("\t", 1)[1].removeprefix("refs/tags/")
        for line in out.splitlines()
        if "\t" in line
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        default=SOURCE_REMOTE,
        help=f"source remote, treated as truth (default: {SOURCE_REMOTE})",
    )
    parser.add_argument(
        "--target",
        default=TARGET_REMOTE,
        help=f"target remote to update (default: {TARGET_REMOTE})",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="print the push commands without changing the target",
    )
    parser.add_argument(
        "--json", action="store_true", help="print a JSON summary"
    )
    args = parser.parse_args()

    known = remotes()
    for name, role in ((args.source, "source"), (args.target, "target")):
        if name not in known:
            raise SystemExit(
                f"{role} remote {name!r} is not configured; add it with:\n"
                f"  git remote add {name} <url>"
            )

    git(["fetch", args.source, "--prune", "--tags"])
    branches = list_branches(args.source)
    tags = list_tags(args.source)
    if not args.dry_run:
        git(["fetch", args.target, "--prune", "--tags"])

    for branch in branches:
        git(
            [
                "push",
                "--force-with-lease",
                args.target,
                f"refs/remotes/{args.source}/{branch}:refs/heads/{branch}",
            ],
            dry_run=args.dry_run,
        )
    for tag in tags:
        git(
            [
                "push",
                "--force",
                args.target,
                f"refs/tags/{tag}:refs/tags/{tag}",
            ],
            dry_run=args.dry_run,
        )

    summary = {
        "source": args.source,
        "target": args.target,
        "dry_run": args.dry_run,
        "branches": branches,
        "tags": tags,
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False), flush=True)
    else:
        print(
            f"synced {len(branches)} branches and {len(tags)} tags "
            f"from {args.source} to {args.target}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
