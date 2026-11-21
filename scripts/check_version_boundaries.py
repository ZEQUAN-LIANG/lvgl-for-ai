from __future__ import annotations

import sys
from pathlib import Path

CONSOLE_ROOT = Path(__file__).resolve().parent.parent / "console"
if str(CONSOLE_ROOT) not in sys.path:
    sys.path.insert(0, str(CONSOLE_ROOT))

import paths

REPO_ROOT = paths.REPO_ROOT
ENGINE_DIR = paths.ENGINE_DIR
ADAPTER_DIR = ENGINE_DIR / "adapter"
USER_APP_DIR = paths.APPS_DIR
ADAPTERS = (
    ADAPTER_DIR / "adapter_9x.c",
    ADAPTER_DIR / "adapter_8x.c",
)

FORBIDDEN_IN_ENGINE = (
    '#include "lvgl.h"',
    "#include <lvgl.h>",
    '#include "lodepng.h"',
    '#include "src/',
)


def check_engine_boundary(failures: list[str]) -> None:
    for adapter in ADAPTERS:
        if not adapter.is_file():
            failures.append(f"{adapter.name}: adapter is missing")
    for path in sorted(ENGINE_DIR.glob("*.c")) + sorted(
        ENGINE_DIR.glob("*.h")
    ):
        text = path.read_text(encoding="utf-8")
        if path in ADAPTERS:
            if '#include "lvgl.h"' not in text:
                failures.append(f"{path.name}: adapter must include lvgl.h")
            continue
        for needle in FORBIDDEN_IN_ENGINE:
            if needle in text:
                failures.append(
                    f"{path.name}: engine source includes {needle}"
                )


def check_user_version_switches(failures: list[str]) -> None:
    for path in (
        USER_APP_DIR / "app.c",
        USER_APP_DIR / "app.h",
        USER_APP_DIR / "lvgl_compat.h",
        USER_APP_DIR / "test_ui" / "test_ui_assets.h",
    ):
        text = path.read_text(encoding="utf-8")
        if "#if LVGL_VERSION_MAJOR" not in text:
            failures.append(
                f"{path.name}: missing #if LVGL_VERSION_MAJOR switch"
            )


def check_obj_name_config(failures: list[str]) -> None:
    text = (ENGINE_DIR / "adapter" / "lv_conf.h").read_text(encoding="utf-8")
    if "#define LV_USE_OBJ_NAME 1" not in text:
        failures.append("lv_conf.h: LV_USE_OBJ_NAME must be enabled for 9.2+")
    if "#ifdef LVGL_MAJOR_8" not in text:
        failures.append(
            "lv_conf.h: missing the separate 8.x configuration block"
        )


def main() -> int:
    failures: list[str] = []
    check_engine_boundary(failures)
    check_user_version_switches(failures)
    check_obj_name_config(failures)
    if failures:
        for failure in failures:
            print(f"FAIL: {failure}", file=sys.stderr)
        return 1
    print(
        "ok: LVGL headers stay in adapter_9x.c / adapter_8x.c; "
        "apps carries version switches; LV_USE_OBJ_NAME is on"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
