from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent.parent
CONSOLE_ROOT = REPO_ROOT / "console"

for path in (REPO_ROOT, CONSOLE_ROOT):
    text = str(path)
    if text not in sys.path:
        sys.path.insert(0, text)

from scripts.tests import support  # noqa: E402,F401

TIER_FAST = "fast"
TIER_ENGINE = "engine"
TIER_INTEGRATION = "integration"
TIER_ALL = "all"
TIERS = (TIER_FAST, TIER_ENGINE, TIER_INTEGRATION, TIER_ALL)

ENV_TIER = "LVGL_VERIFY_LOOP_TEST_TIER"

ENGINE_CLASSES = (
    "scripts.tests.control.test_async_encoding.AsyncEncodingTest",
    "scripts.tests.control.test_changed_frames.ChangedFramesTest",
    "scripts.tests.control.test_errors_logs_checks.BuildFailureSessionTest",
    "scripts.tests.control.test_errors_logs_checks.ChecksIntegrationTest",
    "scripts.tests.control.test_errors_logs_checks.FakeEngineErrorSessionTest",
    "scripts.tests.control.test_errors_logs_checks.MaxFramesIntegrationTest",
    "scripts.tests.control.test_errors_logs_checks.RecordFalseIntegrationTest",
    "scripts.tests.control.test_keypad_encoder.EncoderIntegrationTest",
    "scripts.tests.control.test_keypad_encoder.KeypadIntegrationTest",
    "scripts.tests.control.test_keypad_encoder.KeySequenceDeterminismTest",
    "scripts.tests.control.test_multiversion.EightXInputSemanticsTest",
    "scripts.tests.control.test_multiversion.MultiVersionMatrixTest",
    "scripts.tests.control.test_pointer_timeline.PointerTimelineIntegrationTest",
    "scripts.tests.control.test_runtime.RuntimeIntegrationTest",
    "scripts.tests.control.test_runtime.RuntimeProcessSeamTest",
    "scripts.tests.control.test_scenario.SettingsScenarioIntegrationTest",
    "scripts.tests.control.test_text_input.TextInputEngineIntegrationTest",
    "scripts.tests.control.test_wait_stable.WaitStableEngineIntegrationTest",
    "scripts.tests.engine.test_frame_diffs_manifest.FrameDiffManifestIntegrationTest",
    "scripts.tests.tools.test_cli.CliRealEngineIntegrationTest",
    "scripts.tests.tools.test_contract_snapshot.ContractSnapshotTest",
    "scripts.tests.web.test_web_live.LiveHttpTest",
    "scripts.tests.web.test_web_live.LiveIndependentEngineTest",
    "scripts.tests.web.test_web_live.PageTrackingTest",
)

INTEGRATION_CLASSES = (
    "scripts.tests.engine.test_prebuilt_integration.PrebuiltAutoSelectionIntegrationTest",
    "scripts.tests.release.test_release_integration.ReleaseArtifactIntegrationTest",
    "scripts.tests.web.test_web_live.LiveShutdownIntegrationTest",
)


def _class_of(test_id: str) -> str:
    return test_id.rsplit(".", 1)[0]


def tier_of(test_id: str) -> str:
    owner = _class_of(test_id)
    if owner in INTEGRATION_CLASSES:
        return TIER_INTEGRATION
    if owner in ENGINE_CLASSES:
        return TIER_ENGINE
    return TIER_FAST


def _flatten(suite: unittest.TestSuite):
    for item in suite:
        if isinstance(item, unittest.TestSuite):
            yield from _flatten(item)
        else:
            yield item


def select_tier(suite: unittest.TestSuite, tier: str) -> unittest.TestSuite:
    if tier == TIER_ALL:
        return suite
    kept = [test for test in _flatten(suite) if tier_of(test.id()) == tier]
    return unittest.TestSuite(kept)


def parse_argv(argv: list[str]) -> tuple[str, list[str]]:
    tier = os.environ.get(ENV_TIER, TIER_FAST)
    names: list[str] = []
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--tier":
            index += 1
            if index >= len(argv):
                raise SystemExit("--tier needs a value: " + "|".join(TIERS))
            tier = argv[index]
        elif arg.startswith("--tier="):
            tier = arg.split("=", 1)[1]
        elif arg in ("-h", "--help"):
            raise SystemExit(
                "usage: run_tests.py [--tier fast|engine|integration|all] "
                "[module ...]\n"
                f"  default tier: {TIER_FAST} "
                f"(override with ${ENV_TIER})"
            )
        else:
            names.append(arg)
        index += 1
    if tier not in TIERS:
        raise SystemExit(f"unknown tier {tier!r}: " + "|".join(TIERS))
    return tier, names


def main(argv: list[str] | None = None) -> int:
    tier, names = parse_argv(list(sys.argv[1:] if argv is None else argv))
    loader = unittest.defaultTestLoader
    if names:
        suite = loader.loadTestsFromNames(names)
        if tier != TIER_ALL:
            print(
                f"[tests] tier={tier} ignored for {len(names)} explicit target(s)",
                flush=True,
            )
    else:
        suite = loader.discover(
            str(TESTS_DIR),
            pattern="test_*.py",
            top_level_dir=str(REPO_ROOT),
        )
        suite = select_tier(suite, tier)
    print(f"[tests] tier={tier} tests={suite.countTestCases()}", flush=True)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
