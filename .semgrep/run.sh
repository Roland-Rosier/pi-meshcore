#!/bin/bash
# Run offline semgrep on MeshCore Pi4 rfm9x_sx127x driver files.
# No internet connectivity required — all rules are local in .semgrep/rules/
#
# Usage: uv run .semgrep/run.sh

TMPDIR=$(mktemp -d --tmpdir=/tmp/sandbox/semgrep_tmp)
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
trap 'rm -rf "$TMPDIR"' EXIT

