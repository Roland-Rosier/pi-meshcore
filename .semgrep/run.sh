#!/bin/bash
# Run offline semgrep on MeshCore Pi4 rfm9x_sx127x driver files.
# No internet connectivity required — all rules are local in .semgrep/rules/
#
# Usage: uv run .semgrep/run.sh

uv run semgrep scan --verbose \
  --config=".semgrep/rules/security/" \
       ".semgrep/rules/best-practice/" \
       ".semgrep/rules/correctness/" \
       ".semgrep/rules/maintainability/" \
  src/pi_lora/drivers/rfm9x_sx127x*.py \
  tests/test_rfm9x_sx127x*.py \
  src/pi_lora/framework/*.py \
  tests/framework/*.py

