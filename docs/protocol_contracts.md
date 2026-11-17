# Protocol Contracts

**Enforced requirement:** Every `Protocol` class in `src/pi_lora/` must have a contract test in `tests/contracts/` verifying signature conformance (Liskov Substitution).

## The Contract

A concrete implementation typed against a `Protocol` must be Liskov-substitutable: the implementation's public method signatures must be **compatible** with the protocol's. For optional parameters, the implementation may relax required parameters to optional (widening the accepted call set); the reverse — a protocol requiring parameters the implementation omits — is an LSP violation and a regression.

Contract tests pin this by asserting:

1. **Signature match** — `inspect.signature(Protocol.method).parameters` and `inspect.signature(Implementation.method).parameters` share the same parameter names and default status.
2. **Duck-type conformance** — the concrete object exposes all required protocol members.
3. **Factory contract** — factory returns an *unopened* bus; the caller owns the `open()`/`close()` lifecycle (LSP contract from BUG-5 / Plan-11).

## Example

```python
import inspect

proto_params = [p for p in inspect.signature(SpiBus.open).parameters.values() if p.name != "self"]
impl_params = [p for p in inspect.signature(RealSpiBus.open).parameters.values() if p.name != "self"]
assert [p.name for p in proto_params] == [p.name for p in impl_params]
for p in (*proto_params, *impl_params):
    assert p.default is not inspect.Parameter.empty  # optional, not required
```

## Protocol inventory and coverage

| Protocol | File | Contract test |
|----------|------|---------------|
| `SpiBus` | `src/pi_lora/drivers/spi/bus.py` | `tests/contracts/test_spi_bus_contract.py` ✅ |
| `SpiBusFactory` | `src/pi_lora/drivers/spi/factory.py` | `tests/contracts/test_spi_bus_contract.py` ✅ (via `RealSpiBusFactory`) |
| `SpiLock` | `src/pi_lora/drivers/spi/locks.py` | `tests/contracts/test_spi_bus_contract.py` ✅ |
| `EventHandler` | `src/pi_lora/framework/events.py` | `tests/contracts/test_spi_bus_contract.py` ✅ |
| `SchedulerRegistration` | `src/pi_lora/framework/scheduler.py` | `tests/contracts/test_spi_bus_contract.py` ✅ |

## Reference

- Fixed defect: `SpiBus` protocol signature mismatch (R-2) — protocol relaxed to `open(self, bus: int | None = None, device: int | None = None)` to mirror `RealSpiBus.open`, closing the LSP violation. Verified by `test_protocol_signature_matches_implementation` in `tests/contracts/test_spi_bus_contract.py`.

## Test Infrastructure LSP Compliance (Plan-37 Regression Prevention)

**Test mocks/fakes MUST satisfy the same Protocol contracts as production implementations.** The Liskov Substitution Principle applies to test infrastructure just as it does to production code.

### Mock Factories Must Accept All Protocol Parameters

When a `Protocol` adds optional parameters (e.g., `SpiBusFactory.create()` gained `xfer_timeout: float = 5.0` and `factory_owned: bool = False` in Plan-36 Fix 4), **all mock implementations must be updated** to accept those parameters — even if they ignore them.

**Anti-pattern (LSP VIOLATION)**:
```python
# MockSpiBusFactory — BROKEN after Plan-36 protocol update
def create(
    self,
    bus: int = 0,
    device: int = 0,
) -> SpiBus:
```

**Correct pattern**:
```python
# MockSpiBusFactory — satisfies SpiBusFactory protocol
def create(
    self,
    bus: int = 0,
    device: int = 0,
    *,
    xfer_timeout: float = 5.0,
    factory_owned: bool = False,
) -> SpiBus:
    # Ignore optional params for mock, but accept them for LSP compliance
    ...
```

### Mock Objects Must Implement All Protocol Members

When a `Protocol` adds required members (getters/setters, methods), **all mock implementations must implement them**. In Plan-14 R-2, `SpiBus` protocol gained required property setters for `max_speed_hz`, `mode`, `lsbfirst`, `no_cs`. `MockSpiBus` was missing setters, causing `AttributeError: can't set attribute` when production code set properties on a mock.

**Anti-pattern (LSP VIOLATION)**:
```python
# MockSpiBus — missing required setters
@property
def max_speed_hz(self) -> int:
    return self._max_speed_hz
# No setter → LSP violation
```

**Correct pattern**:
```python
# MockSpiBus — implements all protocol members
@property
def max_speed_hz(self) -> int:
    return self._max_speed_hz

@max_speed_hz.setter
def max_speed_hz(self, value: int) -> None:
    self._max_speed_hz = value
```

### Contract Tests Must Cover All Implementations

Contract tests in `tests/contracts/` must verify **every concrete implementation** (production + test infrastructure), not just production ones.

**Required coverage**:
```python
# tests/contracts/test_spi_bus_contract.py
class TestSpiBusContract:
    @pytest.mark.parametrize("factory", [
        RealSpiBusFactory(),
        MockSpiBusFactory(),  # MUST be included
    ])
    def test_protocol_signature_matches_implementation(self, factory):
        ...

class TestSpiLockContract:
    @pytest.mark.parametrize("lock", [
        aiologic.Lock(),
        MockSpiLock(),  # MUST be included if exists
    ])
    def test_protocol_conformance(self, lock):
        ...
```

### Anti-Regression Checklist for Protocol Changes

When modifying a `Protocol` in `src/pi_lora/`:

1. ✅ Update protocol definition
2. ✅ Update ALL production implementations (`RealSpiBus`, `RealSpiBusFactory`, etc.)
3. ✅ Update ALL test implementations (`MockSpiBus`, `MockSpiBusFactory`, `FakeSpiDev`, etc.)
4. ✅ Verify contract tests include test implementations in parametrization
5. ✅ Run `uv run pytest tests/contracts/` — must pass for ALL implementations
6. ✅ Run `uv run mypy --strict src/` — no LSP errors on mocks

**Failure to update test infrastructure is a regression**, even if production code works correctly. The test suite must exercise the same code paths and satisfy the same contracts.