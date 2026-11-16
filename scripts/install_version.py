"""Install one LVGL version for a local LVGL Verify Loop workspace.

The default package ships LVGL 9.6. This script adds another supported
version in one command:

    python -I scripts/install_version.py --list
    python -I scripts/install_version.py --lvgl 9.4 --source auto
    python -I scripts/install_version.py --lvgl 9.5 --no-build
    python -I scripts/install_version.py --lvgl 9.4 --mode pack \
        --pack path\\to\\version-pack.zip

Source mode wraps ``fetch_lvgl.py``, ``fetch_png.py`` and
``export_sdk.py``, then builds ``apps`` against the exported host SDK
with ``BuildPlan``. It needs CMake, Ninja and GCC for the SDK export, and GCC
for the app build. ``--source auto`` (the default) tries GitHub codeload first;
the Gitee LVGL mirror can return an HTML/400 page, so use ``auto`` or a pack
when it does. Pack mode installs a release asset that already contains
``dist/lvgl/<version>`` and ``build/lvgl_<token>/lvgl_engine``; it needs no compiler
unless the user later changes C code.

All paths are resolved from ``--repo-root`` (default: the detected workspace
root). ``scripts/meta/versions.json`` lists the supported versions, the default and
whether the shipped intro app supports that version. Older checkouts that
still keep ``versions.json`` at the workspace root are accepted as a fallback.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

CONSOLE_ROOT = Path(__file__).resolve().parent.parent / "console"
if str(CONSOLE_ROOT) not in sys.path:
    sys.path.insert(0, str(CONSOLE_ROOT))

import paths
from control.build_plan import BuildPlan
from control.errors import BuildError

INDEX_SCHEMA = "lvgl-verify-loop-versions-v2"
INSTALL_SCHEMA = "lvgl-verify-loop-install-v1"
PACK_SCHEMA = "lvgl-verify-loop-pack-v1"
INDEX_NAME = "versions.json"
_VERSION_RE = re.compile(r"[0-9A-Za-z._-]+")


class InstallError(Exception):
    pass


class ToolError(InstallError):
    pass


def _repo_root(value: Path | None) -> Path:
    root = (value or paths.REPO_ROOT).expanduser().resolve()
    if not (root / "console").is_dir() or not (root / "user" / "app").is_dir():
        raise InstallError(f"not a workspace root: {root}")
    return root


def _metadata_file(repo: Path, name: str) -> Path:
    meta = repo / "scripts" / "meta" / name
    return meta if meta.is_file() else repo / name


def _load_index(repo: Path) -> dict[str, Any]:
    path = _metadata_file(repo, INDEX_NAME)
    if not path.is_file():
        raise InstallError(
            f"{path} is missing; the package should ship scripts/meta/versions.json"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict) or data.get("schema") != INDEX_SCHEMA:
        raise InstallError(f"{path}: schema must be {INDEX_SCHEMA!r}")
    versions = data.get("versions")
    if not isinstance(versions, dict) or not versions:
        raise InstallError(f"{path}: versions must be a non-empty object")
    default = data.get("default")
    if not isinstance(default, str) or default not in versions:
        raise InstallError(f"{path}: default must name a supported version")
    for name, entry in versions.items():
        if not isinstance(name, str) or not _VERSION_RE.fullmatch(name):
            raise InstallError(f"{path}: invalid version name {name!r}")
        if not isinstance(entry, dict):
            raise InstallError(f"{path}: {name} must be an object")
        if not isinstance(entry.get("tag"), str) or not entry["tag"]:
            raise InstallError(f"{path}: {name}.tag must be a string")
        if "sdk" in entry and not isinstance(entry["sdk"], bool):
            raise InstallError(f"{path}: {name}.sdk must be a boolean")
        pack = entry.get("pack")
        if pack is not None:
            if not isinstance(pack, dict):
                raise InstallError(f"{path}: {name}.pack must be an object")
            for key, value in pack.items():
                if not isinstance(value, str):
                    raise InstallError(
                        f"{path}: {name}.pack.{key} must be a string"
                    )
    return data


def _version_entry(index: dict[str, Any], version: str) -> dict[str, Any]:
    entry = index["versions"].get(version)
    if entry is None:
        supported = ", ".join(sorted(index["versions"]))
        raise InstallError(
            f"unsupported LVGL version {version!r}; supported: {supported}"
        )
    return entry


def _tool_version(repo: Path) -> str:
    path = _metadata_file(repo, "VERSION.json")
    if not path.is_file():
        return ""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    value = payload.get("tool_version") if isinstance(payload, dict) else None
    return value if isinstance(value, str) else ""


def _read_pack_manifest(root: Path) -> dict[str, Any] | None:
    path = root / "pack.json"
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise InstallError(f"cannot read pack manifest {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise InstallError(f"pack manifest must be an object: {path}")
    if payload.get("schema") != PACK_SCHEMA:
        raise InstallError(
            f"unsupported pack schema in {path}: {payload.get('schema')!r}"
        )
    return payload


def _check_pack_manifest(
    repo: Path, version: str, root: Path
) -> dict[str, Any] | None:
    manifest = _read_pack_manifest(root)
    if manifest is None:
        return None
    if manifest.get("lvgl") != version:
        raise InstallError(
            f"pack version mismatch: {root} is {manifest.get('lvgl')!r}, "
            f"requested {version!r}"
        )
    expected = manifest.get("core_version") or manifest.get("tool_version")
    actual = _tool_version(repo)
    if expected and actual and expected != actual:
        raise InstallError(
            f"pack requires tool {expected}, but this package is {actual}; "
            "download the matching release assets"
        )
    return manifest


def _build_dir(repo: Path, version: str) -> Path:
    return repo / "build" / f"lvgl_{paths.version_token(version)}"


def _engine_path(repo: Path, version: str) -> Path:
    return _build_dir(repo, version) / paths.engine_filename()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_script(script: str, args: list[str], *, json_mode: bool) -> None:
    command = [
        sys.executable,
        "-I",
        str(Path(__file__).resolve().parent / script),
        *args,
    ]
    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.stdout.strip():
        stream = sys.stderr if json_mode else sys.stdout
        stream.write(result.stdout)
        if not result.stdout.endswith("\n"):
            stream.write("\n")
    if result.stderr.strip():
        sys.stderr.write(result.stderr)
        if not result.stderr.endswith("\n"):
            sys.stderr.write("\n")
    if result.returncode != 0:
        raise ToolError(f"{script} failed with exit code {result.returncode}")


def _safe_zip(archive: zipfile.ZipFile, destination: Path) -> None:
    for info in archive.infolist():
        name = info.filename
        target = Path(name)
        if target.is_absolute() or ".." in target.parts:
            raise InstallError(f"unsafe pack member: {name!r}")
        mode = (info.external_attr >> 16) & 0o170000
        if mode == 0o120000:
            raise InstallError(f"pack contains a symlink: {name!r}")
    archive.extractall(destination)


def _pack_root(root: Path, version: str) -> Path:
    expected = (
        root / "dist" / "lvgl" / version / "manifest.json",
        _engine_path(root, version),
    )
    if all(path.is_file() for path in expected):
        return root
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        if (
            child / "sdk" / version / "manifest.json"
        ).is_file() and _engine_path(child, version).is_file():
            return child
    raise InstallError(
        "pack does not contain dist/lvgl/{0} and build/lvgl_{1}/{2}".format(
            version, paths.version_token(version), paths.engine_filename()
        )
    )


def _download(url: str, destination: Path) -> None:
    request = urllib.request.Request(
        url, headers={"User-Agent": "lvgl-verify-loop"}
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        destination.write_bytes(response.read())


def _download_first(urls: list[str], destination: Path) -> str:
    errors: list[str] = []
    for url in urls:
        try:
            _download(url, destination)
            return url
        except Exception as exc:  # noqa: BLE001 - try the mirror next
            errors.append(f"{url}: {exc}")
    raise InstallError(
        "cannot download version pack; tried:\n  " + "\n  ".join(errors)
    )


def _install_pack(
    repo: Path,
    version: str,
    *,
    pack_path: Path | None,
    pack_urls: list[str] | None,
    sha256: str | None,
    force: bool,
) -> list[str]:
    if pack_path is None and not pack_urls:
        raise InstallError(
            "pack mode needs --pack PATH or --pack-url URL; "
            "use --mode source to download and build instead"
        )
    with tempfile.TemporaryDirectory(prefix="lvgl-version-pack-") as raw:
        work = Path(raw)
        downloaded = pack_path is None
        if pack_path is not None:
            source = pack_path.expanduser().resolve()
            if source.is_dir():
                root = _pack_root(source, version)
                _check_pack_manifest(repo, version, root)
                _copy_pack(repo, root, version, force)
                return ["install_pack"]
            archive_path = source
        else:
            archive_path = work / "pack.zip"
            _download_first(pack_urls or [], archive_path)
        if sha256 is not None:
            actual = _sha256(archive_path)
            if actual != sha256.lower():
                raise InstallError(
                    f"pack sha256 mismatch: expected {sha256}, got {actual}"
                )
        elif downloaded:
            raise InstallError(
                "downloaded packs require --sha256 or pack.sha256 in versions.json"
            )
        if not zipfile.is_zipfile(archive_path):
            raise InstallError(f"pack is not a zip archive: {archive_path}")
        extract = work / "extract"
        extract.mkdir()
        with zipfile.ZipFile(archive_path) as archive:
            _safe_zip(archive, extract)
        root = _pack_root(extract, version)
        _check_pack_manifest(repo, version, root)
        _copy_pack(repo, root, version, force)
        return (
            ["download_pack", "install_pack"]
            if downloaded
            else ["install_pack"]
        )


def _copy_pack(repo: Path, root: Path, version: str, force: bool) -> None:
    for relative in (
        Path("dist") / "lvgl" / version,
        Path("build") / f"lvgl_{paths.version_token(version)}",
    ):
        source = root / relative
        target = repo / relative
        if target.exists():
            if not force:
                raise InstallError(
                    f"{target} already exists; pass --force to replace it"
                )
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target)
    smoke = root / "smoke"
    if smoke.is_dir():
        target = repo / "smoke" / version
        if target.exists():
            if not force:
                raise InstallError(
                    f"{target} already exists; pass --force to replace it"
                )
            shutil.rmtree(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(smoke, target)


def _install_source(
    repo: Path,
    version: str,
    *,
    lvgl_source: str,
    prebuilt: bool,
    build_engine: bool,
    force: bool,
    json_mode: bool,
) -> list[str]:
    actions: list[str] = []
    source = repo / "engine" / "lvgl" / version
    if source.is_dir() and not force:
        actions.append("lvgl-source-present")
    else:
        _run_script(
            "fetch_lvgl.py",
            [
                "--version",
                version,
                "--repo-root",
                str(repo),
                "--source",
                lvgl_source,
            ]
            + (["--force"] if force else []),
            json_mode=json_mode,
        )
        actions.append("fetch_lvgl")

    if (
        (repo / "engine" / "third_party" / "zlib").is_dir()
        and (repo / "engine" / "third_party" / "libpng").is_dir()
        and not force
    ):
        actions.append("png-source-present")
    else:
        _run_script(
            "fetch_png.py",
            ["--repo-root", str(repo)] + (["--force"] if force else []),
            json_mode=json_mode,
        )
        actions.append("fetch_png")

    sdk = repo / "dist" / "lvgl" / version
    if prebuilt:
        if (sdk / "manifest.json").is_file() and not force:
            actions.append("sdk-present")
        else:
            _run_script(
                "export_sdk.py",
                [
                    "--version",
                    version,
                    "--repo-root",
                    str(repo),
                    "--out",
                    str(sdk),
                    "--json",
                ]
                + (["--force"] if force and sdk.exists() else []),
                json_mode=json_mode,
            )
            actions.append("export_sdk")
    else:
        actions.append("source-mode")

    if build_engine:
        plan = BuildPlan(
            version,
            lvgl_src=source,
            build_dir=_build_dir(repo, version),
            engine_dir=repo / "engine",
            user_app_dir=repo / "user" / "app",
            zlib_src=repo / "engine" / "third_party" / "zlib",
            libpng_src=repo / "engine" / "third_party" / "libpng",
            sdk_dir=sdk,
            build_mode="prebuilt" if prebuilt else "source",
        )
        plan.execute(build=True)
        actions.append("build_engine")
    return actions


def _prompt_state_path(repo: Path) -> Path:
    return repo / ".lvgl-verify-loop" / "pack-prompts.json"


def _load_prompt_state(repo: Path) -> dict[str, Any]:
    path = _prompt_state_path(repo)
    if not path.is_file():
        return {"accepted": []}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"accepted": []}
    if not isinstance(payload, dict):
        return {"accepted": []}
    accepted = payload.get("accepted")
    if not isinstance(accepted, list):
        accepted = []
    return {"accepted": [item for item in accepted if isinstance(item, str)]}


def _remember_prompt(repo: Path, version: str) -> None:
    state = _load_prompt_state(repo)
    if version not in state["accepted"]:
        state["accepted"].append(version)
    path = _prompt_state_path(repo)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def ensure_pack_for_version(
    repo: Path,
    version: str,
    *,
    interactive: bool,
    yes: bool = False,
    offline: bool = False,
    force: bool = False,
) -> list[str] | None:
    index = _load_index(repo)
    entry = _version_entry(index, version)
    state = _installed(repo, version)
    if state["source"] or state["sdk"] or state["engine"]:
        return None
    pack = entry.get("pack") or {}
    urls: list[str] = []
    for key in ("gitee", "github"):
        value = pack.get(key)
        if isinstance(value, str) and value and value not in urls:
            urls.append(value)
    if not urls:
        raise InstallError(
            f"LVGL {version} is not installed and has no pack URL; "
            "run install_version.py --mode source"
        )
    if offline:
        raise InstallError(
            f"LVGL {version} is not installed and --offline forbids "
            "downloading its pack"
        )
    accepted = version in _load_prompt_state(repo)["accepted"]
    if not yes and not accepted:
        if not interactive:
            raise InstallError(
                f"LVGL {version} is not installed; run with --yes to download "
                "the pack, or run install_version.py first"
            )
        print(
            f"[version] LVGL {version} is not installed. "
            f"Download the {version} pack? [y/N] ",
            file=sys.stderr,
            end="",
            flush=True,
        )
        answer = sys.stdin.readline().strip().lower()
        if answer not in ("y", "yes"):
            raise InstallError(
                f"LVGL {version} pack was not downloaded; "
                "run install_version.py when ready"
            )
        _remember_prompt(repo, version)
    actions = _install_pack(
        repo,
        version,
        pack_path=None,
        pack_urls=urls,
        sha256=pack.get("sha256") or None,
        force=force,
    )
    if not accepted:
        _remember_prompt(repo, version)
    return actions


def _installed(repo: Path, version: str) -> dict[str, bool]:
    sdk = (repo / "dist" / "lvgl" / version / "manifest.json").is_file()
    engine = _engine_path(repo, version).is_file()
    return {
        "source": (repo / "engine" / "lvgl" / version).is_dir(),
        "sdk": sdk,
        "engine": engine,
        "pack": sdk and engine,
        "smoke": (repo / "smoke" / version).is_dir(),
    }


def _list_versions(repo: Path, index: dict[str, Any], json_mode: bool) -> int:
    rows = []
    for version, entry in sorted(index["versions"].items()):
        state = _installed(repo, version)
        rows.append(
            {
                "version": version,
                "tag": entry["tag"],
                "intro": bool(entry.get("intro", False)),
                "default": version == index["default"],
                **state,
            }
        )
    if json_mode:
        print(
            json.dumps(
                {"schema": INDEX_SCHEMA, "versions": rows},
                ensure_ascii=False,
            )
        )
    else:
        print("version  default  intro  source  sdk  engine  tag")
        for row in rows:
            display = dict(row)
            display.update(
                {
                    "default": "yes" if row["default"] else "",
                    "intro": "yes" if row["intro"] else "",
                    "source": "yes" if row["source"] else "",
                    "sdk": "yes" if row["sdk"] else "",
                    "engine": "yes" if row["engine"] else "",
                }
            )
            print(
                "{version:<7} {default:<8} {intro:<6} {source:<6} "
                "{sdk:<4} {engine:<7} {tag}".format(**display)
            )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="install_version.py",
        description="Install one LVGL version for the local workspace.",
    )
    parser.add_argument("--lvgl", default=None, help="LVGL version, e.g. 9.4")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="workspace root (default: detected from the tool location)",
    )
    parser.add_argument(
        "--mode",
        choices=("auto", "source", "pack"),
        default="auto",
        help="install mode (default: pack when a pack is given, else source)",
    )
    parser.add_argument(
        "--source",
        choices=("auto", "codeload", "gitee"),
        default="auto",
        help=(
            "LVGL source download source; auto tries GitHub codeload first, "
            "then the Gitee mirror"
        ),
    )
    parser.add_argument(
        "--pack",
        type=Path,
        default=None,
        help="local version pack directory or zip",
    )
    parser.add_argument(
        "--pack-url",
        default=None,
        help="version pack URL (requires --sha256 or pack.sha256)",
    )
    parser.add_argument(
        "--sha256",
        default=None,
        help="sha256 for --pack-url",
    )
    parser.add_argument(
        "--pack-source",
        choices=("auto", "github", "gitee"),
        default="auto",
        help="choose a pack URL from versions.json (default: auto)",
    )
    parser.add_argument(
        "--no-build",
        action="store_true",
        help="source mode: export the SDK but do not build apps",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace existing source, SDK, engine or pack files",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list supported versions and installation state",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print exactly one JSON summary on stdout",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        repo = _repo_root(args.repo_root)
        index = _load_index(repo)
        if args.list:
            return _list_versions(repo, index, args.json)
        if not args.lvgl:
            raise InstallError("--lvgl is required unless --list is used")
        entry = _version_entry(index, args.lvgl)
        version = args.lvgl
        pack_urls: list[str] = [args.pack_url] if args.pack_url else []
        sha256 = args.sha256
        pack = entry.get("pack") or {}
        if not pack_urls and args.pack is None and pack:
            keys = (
                ("gitee", "github")
                if args.pack_source == "auto"
                else (args.pack_source,)
            )
            for key in keys:
                url = pack.get(key)
                if isinstance(url, str) and url and url not in pack_urls:
                    pack_urls.append(url)
            sha256 = sha256 or pack.get("sha256")
        mode = args.mode
        if mode == "auto":
            mode = "pack" if (args.pack is not None or pack_urls) else "source"
        if mode == "pack":
            actions = _install_pack(
                repo,
                version,
                pack_path=args.pack,
                pack_urls=pack_urls,
                sha256=sha256,
                force=args.force,
            )
        else:
            actions = _install_source(
                repo,
                version,
                lvgl_source=args.source,
                prebuilt=bool(entry.get("sdk", False)),
                build_engine=not args.no_build,
                force=args.force,
                json_mode=args.json,
            )
        summary = {
            "schema": INSTALL_SCHEMA,
            "version": version,
            "tag": entry["tag"],
            "mode": mode,
            "engine_mode": "prebuilt" if entry.get("sdk") else "source",
            "actions": actions,
            "lvgl_src": str(repo / "engine" / "lvgl" / version),
            "sdk": (
                str(repo / "dist" / "lvgl" / version)
                if mode == "pack" or entry.get("sdk")
                else None
            ),
            "engine": str(_engine_path(repo, version)),
            "smoke": (
                str(repo / "smoke" / version / "legacy_smoke.json")
                if (repo / "smoke" / version / "legacy_smoke.json").is_file()
                else None
            ),
            "status": "ok",
        }
        if args.json:
            print(json.dumps(summary, ensure_ascii=False))
        else:
            print(
                f"[version] {version} installed via {mode}: "
                f"{', '.join(actions)}"
            )
            print(f"[version] sdk: {summary['sdk']}")
            print(f"[version] engine: {summary['engine']}")
        return 0
    except (InstallError, BuildError, OSError, ValueError) as exc:
        print(f"[version] error: {exc}", file=sys.stderr)
        if isinstance(exc, ToolError):
            return 1
        return 2 if isinstance(exc, (InstallError, ValueError)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
