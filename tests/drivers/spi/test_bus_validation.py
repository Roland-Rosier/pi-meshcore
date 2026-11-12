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

"""Validation tests for RealSpiBus xfer_timeout bounds (plan-29 Section 2.5)."""

from __future__ import annotations


def test_xfer_timeout_rejects_infinity_and_nan() -> None:
    """Verify xfer_timeout validation rejects inf, nan, and out-of-bounds values."""
    import pytest

    from pi_lora.drivers.spi.bus import RealSpiBus

    # Test infinity
    with pytest.raises(ValueError, match="finite"):
        RealSpiBus(bus_number=0, device_number=0, xfer_timeout=float('inf'))

    # Test NaN
    with pytest.raises(ValueError, match="finite"):
        RealSpiBus(bus_number=0, device_number=0, xfer_timeout=float('nan'))

    # Test > 3600s upper bound
    with pytest.raises(ValueError, match="3600"):
        RealSpiBus(bus_number=0, device_number=0, xfer_timeout=4000)

    # Test valid value accepted
    bus = RealSpiBus(bus_number=0, device_number=0, xfer_timeout=5.0)
    assert bus._xfer_timeout == 5.0
