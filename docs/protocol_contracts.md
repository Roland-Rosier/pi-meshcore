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
