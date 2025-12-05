# BoneIO Testing Strategy

## Przegląd

Projekt BoneIO wymaga wielopoziomowej strategii testowania ze względu na:
- Zależności od hardware (I2C, GPIO, Modbus, OneWire)
- Asynchroniczną naturę aplikacji (asyncio)
- Integrację z Home Assistant (MQTT)
- Złożoną logikę biznesową (eventy, akcje, stany)

---

## Architektura testów

```
tests/
├── unit/                    # Testy jednostkowe (bez hardware)
│   ├── core/
│   │   ├── test_config.py
│   │   ├── test_events.py
│   │   ├── test_state.py
│   │   └── test_utils.py
│   ├── components/
│   │   ├── test_input_detectors.py
│   │   └── test_output_logic.py
│   └── modbus/
│       ├── test_entities.py
│       └── test_coordinator.py
│
├── integration/             # Testy integracyjne (z mockami hardware)
│   ├── test_manager.py
│   ├── test_mqtt_flow.py
│   └── test_ha_discovery.py
│
├── hardware/                # Testy hardware (tylko na rzeczywistym urządzeniu)
│   ├── test_i2c_devices.py
│   ├── test_gpio.py
│   └── test_modbus_devices.py
│
├── mocks/                   # Mocki i fake'i
│   ├── __init__.py
│   ├── i2c.py              # FakeI2C, MockSMBus
│   ├── gpio.py             # MockGPIO
│   ├── mqtt.py             # MockMQTTClient
│   └── modbus.py           # MockModbusClient
│
├── fixtures/                # Dane testowe
│   ├── configs/
│   │   ├── minimal.yaml
│   │   ├── full.yaml
│   │   └── invalid.yaml
│   └── responses/
│       ├── modbus_cwt.json
│       └── i2c_mcp23017.json
│
└── conftest.py              # Wspólne fixtures pytest
```

---

## Poziomy testowania

### 1. Testy jednostkowe (Unit Tests)

**Cel:** Testowanie izolowanej logiki bez zależności zewnętrznych.

**Co testować:**
- `core/config/` - parsowanie YAML, walidacja schema
- `core/events/` - EventBus, propagacja eventów
- `core/state/` - StateManager
- `core/utils/` - TimePeriod, Filter, utility functions
- `components/input/detectors.py` - MultiClickDetector logika
- `modbus/entities/` - konwersja wartości, filtry

**Przykład:**
```python
# tests/unit/core/test_events.py
import pytest
from boneio.core.events import EventBus, InputEvent

def test_event_bus_subscribe_and_emit():
    bus = EventBus()
    received = []
    
    def handler(event):
        received.append(event)
    
    bus.subscribe("input", handler)
    bus.emit(InputEvent(entity_id="test", click_type="single"))
    
    assert len(received) == 1
    assert received[0].entity_id == "test"
```

### 2. Testy z mockami hardware (Integration with Mocks)

**Cel:** Testowanie przepływów bez rzeczywistego hardware.

**Strategia mockowania:**

```python
# tests/mocks/i2c.py
class MockSMBus:
    """Mock SMBus dla testów bez hardware."""
    
    def __init__(self, bus_number: int = 2):
        self.bus_number = bus_number
        self._registers: dict[int, dict[int, int]] = {}  # addr -> {reg: value}
        self._locked = False
    
    def write_byte_data(self, addr: int, register: int, value: int) -> None:
        if addr not in self._registers:
            self._registers[addr] = {}
        self._registers[addr][register] = value
    
    def read_byte_data(self, addr: int, register: int) -> int:
        return self._registers.get(addr, {}).get(register, 0)
    
    def write_i2c_block_data(self, addr: int, register: int, data: list[int]) -> None:
        for i, byte in enumerate(data):
            self.write_byte_data(addr, register + i, byte)
    
    def read_i2c_block_data(self, addr: int, register: int, length: int) -> list[int]:
        return [self.read_byte_data(addr, register + i) for i in range(length)]


class MockSMBus2I2C:
    """Mock SMBus2I2C wrapper."""
    
    def __init__(self, bus_number: int = 2):
        self._bus = MockSMBus(bus_number)
        self._locked = False
    
    def try_lock(self) -> bool:
        if self._locked:
            return False
        self._locked = True
        return True
    
    def unlock(self) -> None:
        self._locked = False
    
    def __enter__(self):
        self.try_lock()
        return self
    
    def __exit__(self, *args):
        self.unlock()
    
    def writeto(self, address: int, buffer: bytes) -> None:
        for i, byte in enumerate(buffer):
            self._bus.write_byte_data(address, i, byte)
    
    def readfrom_into(self, address: int, buffer: bytearray) -> None:
        for i in range(len(buffer)):
            buffer[i] = self._bus.read_byte_data(address, i)
    
    def writeto_then_readfrom(self, address: int, buffer_out: bytes, buffer_in: bytearray) -> None:
        register = buffer_out[0] if buffer_out else 0
        for i in range(len(buffer_in)):
            buffer_in[i] = self._bus.read_byte_data(address, register + i)
    
    def scan(self) -> list[int]:
        return list(self._registers.keys())
```

### 3. Testy hardware (Hardware Tests)

**Cel:** Weryfikacja na rzeczywistym urządzeniu.

**Uruchamianie:** Tylko na BeagleBone z podłączonym hardware.

```bash
# Oznaczenie testów hardware
pytest tests/hardware/ -m hardware --tb=short

# Pominięcie testów hardware na CI
pytest tests/ -m "not hardware"
```

---

## Implementacja - Etapy

### Etap 1: Infrastruktura (PRIORYTET)
- [ ] Utworzenie struktury katalogów `tests/`
- [ ] Konfiguracja pytest (`pyproject.toml` lub `pytest.ini`)
- [ ] Podstawowe mocki: `MockSMBus2I2C`, `MockMQTTClient`
- [ ] Fixtures w `conftest.py`

### Etap 2: Testy core/ (łatwe, bez hardware)
- [ ] `test_timeperiod.py` - TimePeriod parsing
- [ ] `test_filter.py` - Filter logic
- [ ] `test_yaml_util.py` - YAML loading
- [ ] `test_events.py` - EventBus

### Etap 3: Testy components/
- [ ] `test_multiclick_detector.py` - click detection logic
- [ ] `test_output_base.py` - output state management

### Etap 4: Testy modbus/
- [ ] `test_modbus_entities.py` - entity value conversion
- [ ] `test_modbus_coordinator.py` - coordinator logic (z mockiem)

### Etap 5: Testy integracyjne
- [ ] `test_manager_flow.py` - pełny przepływ z mockami
- [ ] `test_ha_discovery.py` - generowanie discovery messages

---

## Konfiguracja pytest

```toml
# pyproject.toml - sekcja do dodania

[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_functions = ["test_*"]
asyncio_mode = "auto"
markers = [
    "hardware: tests requiring real hardware (deselect with '-m not hardware')",
    "slow: slow tests (deselect with '-m not slow')",
    "integration: integration tests",
]
filterwarnings = [
    "ignore::DeprecationWarning",
]

[tool.pytest]
addopts = "-v --tb=short"
```

---

## Przykładowe testy do implementacji

### 1. TimePeriod (najprostszy start)

```python
# tests/unit/core/test_timeperiod.py
import pytest
from boneio.core.utils.timeperiod import TimePeriod

class TestTimePeriod:
    def test_from_seconds(self):
        tp = TimePeriod(seconds=30)
        assert tp.total_milliseconds == 30000
    
    def test_from_milliseconds(self):
        tp = TimePeriod(milliseconds=500)
        assert tp.total_milliseconds == 500
    
    def test_from_minutes(self):
        tp = TimePeriod(minutes=2)
        assert tp.total_milliseconds == 120000
    
    def test_from_string_seconds(self):
        tp = TimePeriod.from_string("30s")
        assert tp.total_milliseconds == 30000
    
    def test_from_string_milliseconds(self):
        tp = TimePeriod.from_string("500ms")
        assert tp.total_milliseconds == 500
    
    def test_combined(self):
        tp = TimePeriod(minutes=1, seconds=30)
        assert tp.total_milliseconds == 90000
```

### 2. MultiClickDetector

```python
# tests/unit/components/test_multiclick_detector.py
import pytest
import asyncio
from unittest.mock import AsyncMock
from boneio.components.input.detectors import MultiClickDetector

class TestMultiClickDetector:
    @pytest.fixture
    def detector(self):
        callback = AsyncMock()
        return MultiClickDetector(
            input_id="test_input",
            callback=callback,
            double_click_timeout=0.3,
            long_press_timeout=0.8
        )
    
    @pytest.mark.asyncio
    async def test_single_click(self, detector):
        await detector.handle_press()
        await asyncio.sleep(0.05)
        await detector.handle_release()
        await asyncio.sleep(0.4)  # Wait for timeout
        
        detector._callback.assert_called_once()
        call_args = detector._callback.call_args
        assert call_args[1]["click_type"] == "single"
    
    @pytest.mark.asyncio
    async def test_double_click(self, detector):
        # First click
        await detector.handle_press()
        await asyncio.sleep(0.05)
        await detector.handle_release()
        
        # Second click within timeout
        await asyncio.sleep(0.1)
        await detector.handle_press()
        await asyncio.sleep(0.05)
        await detector.handle_release()
        
        await asyncio.sleep(0.4)  # Wait for timeout
        
        # Should detect double click
        calls = detector._callback.call_args_list
        assert any(c[1]["click_type"] == "double" for c in calls)
```

### 3. MCP23017 z mockiem

```python
# tests/unit/hardware/test_mcp23017.py
import pytest
from tests.mocks.i2c import MockSMBus2I2C
from boneio.hardware.gpio.expanders.mcp23017 import MCP23017

class TestMCP23017:
    @pytest.fixture
    def mock_i2c(self):
        return MockSMBus2I2C(bus_number=2)
    
    @pytest.fixture
    def mcp(self, mock_i2c):
        return MCP23017(i2c=mock_i2c, address=0x20, reset=False)
    
    def test_initialization(self, mcp, mock_i2c):
        # Check IODIR registers set to output (0x00)
        assert mock_i2c._bus._registers[0x20][0x00] == 0x00  # IODIRA
        assert mock_i2c._bus._registers[0x20][0x01] == 0x00  # IODIRB
    
    def test_set_pin_high(self, mcp, mock_i2c):
        mcp.set_pin_value(0, True)
        # Check OLATA register
        assert mock_i2c._bus._registers[0x20][0x14] & 0x01 == 0x01
    
    def test_set_pin_low(self, mcp, mock_i2c):
        mcp.set_pin_value(0, True)
        mcp.set_pin_value(0, False)
        assert mock_i2c._bus._registers[0x20][0x14] & 0x01 == 0x00
    
    def test_pin_on_port_b(self, mcp, mock_i2c):
        mcp.set_pin_value(8, True)  # Pin 8 is on Port B
        # Check OLATB register
        assert mock_i2c._bus._registers[0x20][0x15] & 0x01 == 0x01
```

---

## Uruchamianie testów

```bash
# Wszystkie testy (bez hardware)
pytest tests/ -m "not hardware"

# Tylko testy jednostkowe
pytest tests/unit/

# Konkretny moduł
pytest tests/unit/core/test_timeperiod.py -v

# Z coverage
pytest tests/ -m "not hardware" --cov=boneio --cov-report=html

# Testy hardware (tylko na BeagleBone)
pytest tests/hardware/ -m hardware
```

---

## CI/CD (GitHub Actions)

```yaml
# .github/workflows/tests.yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      
      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.13'
      
      - name: Install dependencies
        run: |
          pip install -e ".[dev]"
          pip install pytest pytest-asyncio pytest-cov
      
      - name: Run tests
        run: pytest tests/ -m "not hardware" --cov=boneio
```

---

## Następne kroki

1. **Zacznij od Etapu 1** - stwórz strukturę i podstawowe mocki
2. **Napisz pierwsze testy** - `test_timeperiod.py` (najprostsze)
3. **Iteruj** - dodawaj testy wraz z rozwojem kodu

Kiedy będziesz gotowy, podaj mi ten plik, a pomogę z implementacją konkretnych testów.
