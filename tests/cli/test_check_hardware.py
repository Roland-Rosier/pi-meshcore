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

"""Tests for ``pi_lora.cli.check_hardware._normalise_module_type``.

Exercises the Plan-19 Fix 2 contract: the normaliser accepts case-insensitive,
whitespace-trimmed CLI aliases and returns the canonical LoRa module type, raising
``typer.BadParameter`` for anything unrecognised.
"""

from typing import Literal

import pytest
import typer

from pi_lora.cli.check_hardware import _normalise_module_type


def test_check_hardware_mapping_type_annotation() -> None:
    """Canonicalise every accepted alias, cover ``None`` and a rejected value.

    Covers the five canonical mappings, whitespace trimming, and case
    insensitivity (the aliases that Plan-19 Fix 2 added to the mapping key type).
    """
    aliases: tuple[tuple[str, Literal["rfm95w", "rfm98w", "none"]], ...] = (
        ("rfm95w", "rfm95w"),
        ("sx1276", "rfm95w"),
        ("rfm98w", "rfm98w"),
        ("sx1278", "rfm98w"),
        ("none", "none"),
        ("  SX1276  ", "rfm95w"),
        ("Rfm98W", "rfm98w"),
    )
    for alias, canonical in aliases:
        assert _normalise_module_type(alias) == canonical

    assert _normalise_module_type(None) is None

    with pytest.raises(typer.BadParameter):
        _normalise_module_type("bogus")
