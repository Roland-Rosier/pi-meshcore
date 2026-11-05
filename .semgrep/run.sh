#!/bin/bash
# Run offline semgrep on MeshCore Pi4 rfm9x_sx127x driver files.
# No internet connectivity required — all rules are local in .semgrep/rules/
#
# Usage: uv run .semgrep/run.sh

# PLAN-22 (Section 6, Item 11): mkdir -p ensures temp parent exists; trap handles EXIT INT TERM for cleanup on Ctrl+C/kill.
# Item 11: `mktemp -d --tmpdir=...` is not universally supported on non-GNU systems; the POSIX-compliant form uses the `TMPDIR=... mktemp -d` construct where `TMPDIR` is a standard environment variable.
mkdir -p /tmp/sandbox/semgrep_tmp
TMPDIR=$(TMPDIR=/tmp/sandbox/semgrep_tmp mktemp -d)
uv run semgrep scan --verbose \
   --config=".semgrep/rules/security/" \
   --config=".semgrep/rules/best-practice/" \
   --config=".semgrep/rules/correctness/" \
   --config=".semgrep/rules/maintainability/" \
   --config=".semgrep/rules/custom/" \
  src/pi_lora/drivers/rfm9x_sx127x*.py \
  tests/test_rfm9x_sx127x*.py \
  src/pi_lora/framework/*.py \
  tests/framework/*.py \
  src/pi_lora/drivers/spi/*.py \
  tests/spi/*.py \
  src/pi_lora/cli/config.py \
  tests/test_config_*.py
trap 'rm -rf "$TMPDIR"' EXIT INT TERM

