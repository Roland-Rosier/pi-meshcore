# Copyright 2026 Roland Rosier
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# see the License for the specific language governing permissions and
# limitations under the License.

"""CLI tests for check_hardware.py — Phase 1 of remediation plan.

Tests the Typer-based CLI entry-point by invoking it through
typer.testing.CliRunner with mocked LoRaModuleDetector so that
every test produces deterministic, hardware-independent results.
"""

from __future__ import annotations

import sys
from io import StringIO
from typing import Any, Callable, Dict, List, Optional
from unittest.mock import MagicMock, patch

import pytest
import typer
from typer.testing import CliRunner

from src.cli.check_hardware import app as cli_app
from tests.fakes import FakeSpiDev


# ---------------------------------------------------------------------------
# Helpers — SPI factory that alternates between two FakeSpiDev instances
# ---------------------------------------------------------------------------

def _make_dual_spi_factory(
    fake_ce0: FakeSpiDev, fake_ce1: FakeSpiDev
) -> Callable[[], FakeSpiDev]:
    """Return a factory that yields *fake_ce0* on call 1 and *fake_ce1* on call 2."""
    _counter: list[int] = [0]

    def factory() -> FakeSpiDev:
        _counter[0] += 1
        return fake_ce0 if _counter[0] == 1 else fake_ce1

    return factory


# ---------------------------------------------------------------------------
# Shared fixtures — provide pre-configured FakeSpiDev instances that can be
# reused across multiple tests without state leakage.
# ---------------------------------------------------------------------------

@pytest.fixture()
def fake_rfm95w_spi() -> FakeSpiDev:
    """Provide a Fresh FakeSpiDev configured as an RFM95W."""
    return FakeSpiDev(module_type="rfm95w")


@pytest.fixture()
def fake_rfm98w_spi() -> FakeSpiDev:
    """Provide a fresh FakeSpiDev configured as an RFM98W."""
    return FakeSpiDev(module_type="rfm98w")


# ---------------------------------------------------------------------------
# Patching strategy
# ---------------------------------------------------------------------------

# The CLI function ``detect_modules`` (in check_hardware.py) creates a
# LoRaModuleDetector internally.  We patch the detector's *constructor* so that
# every test can supply its own fake modules without touching real SPI hardware.
#
# Patch target: src.cli.check_hardware.LoRaModuleDetector  OR
#               src.drivers.lora_detection.LoRaModuleDetector
# Both paths resolve to the same class; patching at the CLI import site is
# more robust because it does not depend on where LoRaModuleDetector was
# originally imported from.

_DETECTOR_PATCH_PATH: str = "src.cli.check_hardware.LoRaModuleDetector"


def _build_mock_detector(
    ce_pins: List[int],
    module_type_strings: Optional[List[str]] = None,
    communication_successes: Optional[List[bool]] = None,
) -> MagicMock:
    """Build a LoRaModuleDetector mock with predictable properties.

    Parameters
    ----------
    ce_pins : list[int]
        The CE pin numbers the detector was "initialized" with (for debugging).
    module_type_strings : list[str], optional
        Module type strings returned by each mocked LoRaModule instance.
    communication_successes : list[bool], optional
        Whether each module reported successful SPI communication.

    Returns
    -------
    MagicMock
        A mock LoRaModuleDetector whose ``modules`` attribute is a list of
        MagicMock objects that behave like real LoRaModule instances, and whose
        ``detect_modules()`` returns predictable detection-result dicts.
    """
    if module_type_strings is None:
        module_type_strings = ["Unknown / Communication Error"] * len(ce_pins)
    if communication_successes is None:
        communication_successes = [False] * len(ce_pins)

    # Build individual LoRaModule mock instances.
    modules: list[MagicMock] = []
    for idx, ce_pin in enumerate(ce_pins):
        mod = MagicMock()
        mod.ce_pin = ce_pin
        mod.module_type = module_type_strings[idx]
        mod.communication_success = communication_successes[idx]
        mod.silicon_revision = 0x12 if communication_successes[idx] else None

        # read_register returns a plausible value so that detect_modules()
        # does not produce "None read" strings.
        mod.read_register.return_value = 0x42

        modules.append(mod)

    detector_mock = MagicMock()
    detector_mock.modules = modules
    detector_mock.ce_pins = ce_pins

    def _detect_modules(
        config: Optional[Any] = None,
    ) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for mod in modules:
            result: Dict[str, Any] = {
                "ce_pin": mod.ce_pin,
                "module_type": mod.module_type,
                "Silicon Revision": (
                    f"0x{mod.silicon_revision:02X}"
                    if mod.silicon_revision is not None
                    else "None detected"
                ),
                "reg_rxbw_freqifmsb": "0x42",
            }
            results.append(result)

        # Extended detection fields for dual-CE scenarios.
        if len(results) >= 2:
            for result in results:
                result["is_single_module_dual_spi"] = False
                result["unique_value_written"] = True
                result["unique_value_verified"] = True

        return results

    detector_mock.detect_modules.side_effect = _detect_modules
    return detector_mock


# ---------------------------------------------------------------------------
# Test 1 — detect-modules with NO validation args
# ---------------------------------------------------------------------------

class TestDetectModulesNoValidation:
    """Phase 1, test 1 of the remediation plan."""

    def test_detect_modules_no_validation(self) -> None:
        """Run ``detect-modules`` with no CE options.

        Verify:
          - Exit code is 0.
          - Output contains "Hardware Detection Results:".
          - At least one line starts with "✅".
        """
        runner = CliRunner()
        mock_detector = _build_mock_detector(
            ce_pins=[0, 1],
            module_type_strings=[
                "RFM95W (High-Band 868MHz / Semtech SX1276)",
                "RFM98W (Low-Band 433Mhz / Semtech SX1278)",
            ],
            communication_successes=[True, True],
        )

        with patch(_DETECTOR_PATCH_PATH, return_value=mock_detector):
            result = runner.invoke(cli_app, ["detect-modules"])

        assert result.exit_code == 0, (
            f"Expected exit code 0 but got {result.exit_code}. "
            f"Output: {result.output}"
        )
        assert "Hardware Detection Results:" in result.output
        assert "\u2705" in result.output  # checkmark emoji


# ---------------------------------------------------------------------------
# Test 2 — matching config on CE0 (ce0=rfm95w, detected rfm95w)
# ---------------------------------------------------------------------------

class TestDetectModulesMatchingConfig:
    """Phase 1, test 2 of the remediation plan."""

    def test_detect_modules_matching_config_ce0(self) -> None:
        """Run ``detect-modules --ce0 rfm95w`` when CE0 is actually RFM95W.

        Verify:
          - Exit code is 0.
          - Output contains "Configuration is valid.".
        """
        runner = CliRunner()
        mock_detector = _build_mock_detector(
            ce_pins=[0, 1],
            module_type_strings=[
                "RFM95W (High-Band 868MHz / Semtech SX1276)",
                "RFM98W (Low-Band 433Mhz / Semtech SX1278)",
            ],
            communication_successes=[True, True],
        )

        # The validate_config method must return a single ValidationResult for CE0.
        from src.drivers.lora_detection import ValidationResult

        mock_detector.validate_config.return_value = [
            ValidationResult(
                ce_pin=0,
                passed=True,
                message="Expected: rfm95w, Detected: RFM95W (High-Band 868MHz / Semtech SX1276) (Match)",
                expected_type="rfm95w",
                detected_type="RFM95W (High-Band 868MHz / Semtech SX1276)",
            ),
        ]

        with patch(_DETECTOR_PATCH_PATH, return_value=mock_detector):
            result = runner.invoke(cli_app, ["detect-modules", "--ce0", "rfm95w"])

        assert result.exit_code == 0, (
            f"Expected exit code 0 but got {result.exit_code}. "
            f"Output: {result.output}"
        )
        assert "Configuration is valid." in result.output


# ---------------------------------------------------------------------------
# Test 3 — mismatching config on CE1 (ce1=rfm95w, detected rfm98w)
# ---------------------------------------------------------------------------

class TestDetectModulesMismatchingConfig:
    """Phase 1, test 3 of the remediation plan."""

    def test_detect_modules_mismatching_config_ce1(self) -> None:
        """Run ``detect-modules --ce1 rfm95w`` when CE1 is actually RFM98W.

        Verify:
          - Exit code is non-zero (Typer.Exit(code=1)).
          - Output contains "❌ FAIL".
          - Output contains the word "Mismatch".
        """
        runner = CliRunner()
        mock_detector = _build_mock_detector(
            ce_pins=[0, 1],
            module_type_strings=[
                "RFM95W (High-Band 868MHz / Semtech SX1276)",
                "RFM98W (Low-Band 433Mhz / Semtech SX1278)",
            ],
            communication_successes=[True, True],
        )

        from src.drivers.lora_detection import ValidationResult

        mock_detector.validate_config.return_value = [
            ValidationResult(
                ce_pin=1,
                passed=False,
                message="Expected: rfm95w, Detected: RFM98W (Low-Band 433Mhz / Semtech SX1278) (Mismatch)",
                expected_type="rfm95w",
                detected_type="RFM98W (Low-Band 433Mhz / Semtech SX1278)",
            ),
        ]

        with patch(_DETECTOR_PATCH_PATH, return_value=mock_detector):
            result = runner.invoke(cli_app, ["detect-modules", "--ce1", "rfm95w"])

        assert result.exit_code != 0, (
            f"Expected non-zero exit code but got {result.exit_code}. "
            f"Output: {result.output}"
        )
        assert "\u274c FAIL" in result.output or "FAIL" in result.output
        assert "Mismatch" in result.output


# ---------------------------------------------------------------------------
# Test 4 — dual-CE validation (ce0=rfm95w, ce1=rfm98w)
# ---------------------------------------------------------------------------

class TestDetectModulesDualCeValidation:
    """Phase 1, test 4 of the remediation plan."""

    def test_detect_modules_dual_ce_validation(self) -> None:
        """Run ``detect-modules --ce0 rfm95w --ce1 rfm98w`` with matching hardware.

        Verify:
          - All validations pass.
          - Exit code is 0.
          - Output contains "Configuration is valid.".
        """
        runner = CliRunner()
        mock_detector = _build_mock_detector(
            ce_pins=[0, 1],
            module_type_strings=[
                "RFM95W (High-Band 868MHz / Semtech SX1276)",
                "RFM98W (Low-Band 433Mhz / Semtech SX1278)",
            ],
            communication_successes=[True, True],
        )

        from src.drivers.lora_detection import ValidationResult

        mock_detector.validate_config.return_value = [
            ValidationResult(
                ce_pin=0,
                passed=True,
                message="Expected: rfm95w, Detected: RFM95W (High-Band 868MHz / Semtech SX1276) (Match)",
                expected_type="rfm95w",
                detected_type="RFM95W (High-Band 868MHz / Semtech SX1276)",
            ),
            ValidationResult(
                ce_pin=1,
                passed=True,
                message="Expected: rfm98w, Detected: RFM98W (Low-Band 433Mhz / Semtech SX1278) (Match)",
                expected_type="rfm98w",
                detected_type="RFM98W (Low-Band 433Mhz / Semtech SX1278)",
            ),
        ]

        with patch(_DETECTOR_PATCH_PATH, return_value=mock_detector):
            result = runner.invoke(
                cli_app, ["detect-modules", "--ce0", "rfm95w", "--ce1", "rfm98w"]
            )

        assert result.exit_code == 0, (
            f"Expected exit code 0 but got {result.exit_code}. "
            f"Output: {result.output}"
        )
        assert "\u2705 PASS" in result.output
        assert "Configuration is valid." in result.output


# ---------------------------------------------------------------------------
# Test 5 — invocation without subcommand (help text)
# ---------------------------------------------------------------------------

class TestNoSubcommandShowsHelp:
    """Phase 1, test 5 of the remediation plan."""

    def test_no_subcommand_shows_help(self) -> None:
        """Invoke CLI without a subcommand.

        Verify:
          - Output contains "Usage: check-hardware [command]".
          - Exit code is 0.
          - Output lists ``detect-modules`` as an available command.
        """
        runner = CliRunner()

        # No arguments at all — triggers the callback's invoke_without_command path.
        result = runner.invoke(cli_app, [])

        assert result.exit_code == 0, (
            f"Expected exit code 0 but got {result.exit_code}. "
            f"Output: {result.output}"
        )
        assert "Usage: check-hardware [command]" in result.output
        assert "detect-modules" in result.output


# ---------------------------------------------------------------------------
# Test 6 — detect-modules with --ce1 none (detected rfm98w → mismatch)
# ---------------------------------------------------------------------------

class TestDetectModulesWithNoneExpectation:
    """Phase 1, test 6 of the remediation plan."""

    def test_detect_modules_with_none_expectation(self) -> None:
        """Run ``detect-modules --ce1 none`` when CE1 actually has an RFM98W.

        Verify:
          - Exit code is non-zero (detected hardware does not match "none" expectation).
          - Output contains "❌ FAIL".
        """
        runner = CliRunner()
        mock_detector = _build_mock_detector(
            ce_pins=[0, 1],
            module_type_strings=[
                "RFM95W (High-Band 868MHz / Semtech SX1276)",
                "RFM98W (Low-Band 433Mhz / Semtech SX1278)",
            ],
            communication_successes=[True, True],
        )

        from src.drivers.lora_detection import ValidationResult

        # Expecting 'none' but detecting RFM98W → mismatch.
        mock_detector.validate_config.return_value = [
            ValidationResult(
                ce_pin=1,
                passed=False,
                message="Expected: none, Detected: RFM98W (Low-Band 433Mhz / Semtech SX1278) (Mismatch)",
                expected_type="none",
                detected_type="RFM98W (Low-Band 433Mhz / Semtech SX1278)",
            ),
        ]

        with patch(_DETECTOR_PATCH_PATH, return_value=mock_detector):
            result = runner.invoke(cli_app, ["detect-modules", "--ce1", "none"])

        assert result.exit_code != 0, (
            f"Expected non-zero exit code but got {result.exit_code}. "
            f"Output: {result.output}"
        )
        assert "\u274c FAIL" in result.output or "FAIL" in result.output


# ---------------------------------------------------------------------------
# Additional CLI-level edge-case tests (bonus coverage beyond the plan)
# ---------------------------------------------------------------------------

class TestCliEdgeCases:
    """Extra CLI tests for robustness — not explicitly listed in Phase 1."""

    def test_detect_modules_with_invalid_module_type(self) -> None:
        """Typer should reject an invalid ModuleType value.

        The ``ModuleType`` enum only allows "rfm95w", "rfm98w", and "none".
        Passing anything else is a Typer-level validation error, not our code's.
        """
        runner = CliRunner()
        result = runner.invoke(cli_app, ["detect-modules", "--ce0", "invalid_type"])

        assert result.exit_code != 0
        # Typer prints usage + an error message for invalid option values.
        assert ("Invalid value" in result.output or "error" in result.output.lower())

    def test_output_format_single_pin_mismatch(self) -> None:
        """Verify full output format for single-pin mismatch scenario.

        A single-pin detector (CE1 only) with a CE0 expectation set will produce
        a validation mismatch — the CLI should report "FAIL" with ``CE0:`` in the
        output and return a non-zero exit code.  This covers the minor gap m2:
        previously the test only asserted that no crash occurred, without checking
        any output content or exit code semantics.
        """
        runner = CliRunner()
        mock_detector = _build_mock_detector(
            ce_pins=[1],  # Only CE1 exists in this detector
            module_type_strings=["RFM98W (Low-Band 433Mhz / Semtech SX1278)"],
            communication_successes=[True],
        )

        from src.drivers.lora_detection import ValidationResult

        mock_detector.validate_config.return_value = [
            ValidationResult(
                ce_pin=0,
                passed=False,
                message="Expected: rfm95w, Detected: RFM98W (Low-Band 433Mhz / Semtech SX1278) (Mismatch)",
                expected_type="rfm95w",
                detected_type="RFM98W (Low-Band 433Mhz / Semtech SX1278)",
            ),
        ]

        with patch(_DETECTOR_PATCH_PATH, return_value=mock_detector):
            result = runner.invoke(cli_app, ["detect-modules", "--ce0", "rfm95w"])

        assert result.exit_code != 0, (
            f"Expected non-zero exit code for mismatch but got {result.exit_code}. "
            f"Output: {result.output}"
        )
        assert "\u274c FAIL" in result.output or "FAIL" in result.output, (
            f"Expected 'FAIL' in output but got: {result.output}"
        )
        assert "CE0:" in result.output, (
            f"Expected 'CE0:' label in validation output but got: {result.output}"
        )

    def test_output_format_contains_silicon_revision(self) -> None:
        """Verify that Silicon Revision appears in detection output."""
        runner = CliRunner()
        mock_detector = _build_mock_detector(
            ce_pins=[0],
            module_type_strings=["RFM95W (High-Band 868MHz / Semtech SX1276)"],
            communication_successes=[True],
        )

        with patch(_DETECTOR_PATCH_PATH, return_value=mock_detector):
            result = runner.invoke(cli_app, ["detect-modules"])

        assert result.exit_code == 0
        assert "Silicon Revision" in result.output
        assert "0x12" in result.output


if __name__ == "__main__":
    """Run tests using pytest."""
    import sys as _sys

    exit_code = pytest.main([__file__, "-v"])
    _sys.exit(exit_code)




