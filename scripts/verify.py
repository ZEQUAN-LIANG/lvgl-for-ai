from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Sequence

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
PYTHON = sys.executable


def run(
    args: Sequence[str],
    *,
    cwd: Path = REPO_ROOT,
    timeout: float | None = None,
) -> dict[str, Any]:
    command = [PYTHON, "-I", "-B", *args]
    result = subprocess.run(
        command,
        cwd=str(cwd),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    return {
        "command": " ".join(command),
        "returncode": result.returncode,
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def _step(name: str, outcome: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": name,
        "ok": outcome["returncode"] == 0,
        "returncode": outcome["returncode"],
        "command": outcome["command"],
        "stderr_tail": outcome["stderr"][-1500:],
        "stdout_tail": outcome["stdout"][-1500:],
    }


def check_package_root(package: Path) -> list[str]:
    errors: list[str] = []
    files = sorted(path.name for path in package.iterdir() if path.is_file())
    if files != ["SKILL.md"]:
        errors.append(f"package root files must be ['SKILL.md'], got {files}")
    for relative in (
        "api-nav",
        "console",
        "engine",
        "user/app",
        "user/scenarios",
        "scripts",
        "bin/lvgl.cmd",
        "dist/lvgl",
        "build",
        "docs/licenses",
    ):
        if not (package / relative).exists():
            errors.append(f"missing package entry: {relative}")
    for relative in ("engine/lvgl", "engine/third_party", "lvgl-src"):
        if (package / relative).exists():
            errors.append(f"unexpected package entry: {relative}")
    return errors


def verify_package(zip_path: Path) -> dict[str, Any]:
    root = Path(tempfile.mkdtemp(prefix="lvgl-verify-package-"))
    errors: list[str] = []
    checks: list[dict[str, Any]] = []
    try:
        with zipfile.ZipFile(zip_path) as archive:
            archive.extractall(root)
        package = root / "lvgl-verify-loop"
        errors.extend(check_package_root(package))
        runner = package / "scripts" / "lvgl.py"
        for name, args, timeout in (
            (
                "run",
                [
                    str(runner),
                    "run",
                    "--scenario",
                    "user/scenarios/intro.json",
                    "--json",
                ],
                600.0,
            ),
            (
                "report",
                [str(runner), "report", "--latest", "--log-tail", "2"],
                120.0,
            ),
            ("assets", [str(runner), "assets", "doctor", "--json"], 120.0),
        ):
            outcome = run(args, cwd=package, timeout=timeout)
            step = _step(f"package:{name}", outcome)
            checks.append(step)
            if not step["ok"]:
                errors.append(
                    f"package {name} failed: {outcome['stderr'][-500:]}"
                )
    finally:
        shutil.rmtree(root, ignore_errors=True)
    return {"zip": str(zip_path), "errors": errors, "checks": checks}


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="verify.py",
        description="Run lint, contract, tests and release-package verification.",
    )
    parser.add_argument("--skip-lint", action="store_true")
    parser.add_argument("--skip-contract", action="store_true")
    parser.add_argument("--skip-tests", action="store_true")
    parser.add_argument("--skip-package", action="store_true")
    parser.add_argument(
        "--force-build",
        action="store_true",
        help="rebuild package engines instead of reusing the cache",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report: dict[str, Any] = {"steps": [], "package": None, "ok": True}

    def add(name: str, outcome: dict[str, Any]) -> None:
        step = _step(name, outcome)
        report["steps"].append(step)
        report["ok"] = report["ok"] and step["ok"]

    if not args.skip_lint:
        add("lint", run(["scripts/lint.py", "check", "--json"]))
    if not args.skip_contract:
        add(
            "contract",
            run(["scripts/contract_snapshot.py", "compare"], timeout=600.0),
        )
    if not args.skip_tests:
        add("tests", run(["scripts/tests/run_tests.py"], timeout=3600.0))
    if not args.skip_package:
        release_args = [
            "scripts/release_all.py",
            "--out",
            "dist/release",
            "--json",
        ]
        if args.force_build:
            release_args.append("--force-build")
        outcome = run(release_args, timeout=3600.0)
        add("release", outcome)
        if outcome["returncode"] == 0:
            try:
                payload = json.loads(outcome["stdout"].splitlines()[-1])
            except (IndexError, json.JSONDecodeError):
                report["package"] = {
                    "errors": ["cannot parse release summary"]
                }
                report["ok"] = False
            else:
                zip_path = Path(payload["full"]["zip"])
                report["package"] = verify_package(zip_path)
                report["ok"] = report["ok"] and not report["package"]["errors"]

    if args.json:
        print(json.dumps(report, ensure_ascii=False))
    else:
        for step in report["steps"]:
            state = "ok" if step["ok"] else "FAILED"
            print(f"[{state}] {step['name']}: {step['command']}")
            if not step["ok"] and step["stderr_tail"]:
                print(step["stderr_tail"])
        if report["package"] is not None:
            state = "ok" if not report["package"]["errors"] else "FAILED"
            print(f"[{state}] package: {report['package']['zip']}")
            for error in report["package"]["errors"]:
                print(f"  {error}")
        print("OK" if report["ok"] else "FAILED")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
