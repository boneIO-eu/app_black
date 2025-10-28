# MCP23017 Migration to smbus2

## Zmiany

Biblioteka **Adafruit CircuitPython MCP230xx** została zastąpiona własną implementacją opartą na **smbus2**.

### Usunięte zależności
- ❌ `adafruit-circuitpython-mcp230xx==2.5.18`

### Nowa implementacja
- ✅ `boneio.hardware.gpio.expanders.MCP23017` - driver oparty na smbus2
- ✅ Output-only (bez odczytu) - wystarczające dla relay control
- ✅ Pełna kompatybilność API z Adafruit (get_pin(), switch_to_output(), value)

## API

### Przed (Adafruit)
```python
from adafruit_mcp230xx.mcp23017 import MCP23017, DigitalInOut

mcp = MCP23017(i2c=i2c, address=0x20, reset=False)
pin0 = mcp.get_pin(0)
pin0.switch_to_output(value=True)
pin0.value = False
```

### Po (smbus2)
```python
from boneio.hardware.gpio.expanders import MCP23017
from boneio.hardware.gpio.expanders.mcp23017 import DigitalInOut

mcp = MCP23017(i2c=i2c, address=0x20, reset=False)
pin0 = mcp.get_pin(0)
pin0.switch_to_output(value=True)
pin0.value = False
```

**API jest identyczne** - żadne zmiany w kodzie korzystającym z MCP23017 nie są wymagane.

## Architektura

### Rejestry MCP23017
- **IODIRA/IODIRB** (0x00/0x01) - kierunek pinów (0=output, 1=input)
- **OLATA/OLATB** (0x14/0x15) - output latch (zapisz stan)
- Port A: piny 0-7
- Port B: piny 8-15

### Implementacja
1. **Inicjalizacja**: Wszystkie piny ustawiane jako output (IODIR=0x00)
2. **switch_to_output()**: Konfiguruje pin jako output w rejestrze IODIR
3. **value setter**: Zapisuje stan do rejestru OLAT (bit manipulation)
4. **State tracking**: Wewnętrzne śledzenie stanów dla obu portów

### Optymalizacje
- Bezpośrednie użycie SMBus zamiast wrappera dla lepszej wydajności
- Bit manipulation dla pojedynczych pinów bez wpływu na inne
- Minimalna liczba operacji I2C

## Pliki zaktualizowane

1. **Nowe pliki**:
   - `boneio/hardware/__init__.py`
   - `boneio/hardware/i2c/__init__.py`
   - `boneio/hardware/i2c/bus.py` (SMBus2I2C)
   - `boneio/hardware/gpio/__init__.py`
   - `boneio/hardware/gpio/expanders/__init__.py`
   - `boneio/hardware/gpio/expanders/mcp23017.py` ⭐

2. **Zaktualizowane importy**:
   - `boneio/relay/mcp.py`
   - `boneio/core/config/loader.py`
   - `boneio/helper/loader.py`

3. **Zależności**:
   - `pyproject.toml` - usunięto `adafruit-circuitpython-mcp230xx`

## Testowanie

### Syntax check
```bash
python3 -m py_compile boneio/hardware/gpio/expanders/mcp23017.py
python3 -m py_compile boneio/relay/mcp.py
python3 -m py_compile boneio/core/config/loader.py
```

### Import test (wymaga smbus2)
```python
from boneio.hardware.gpio.expanders import MCP23017
from boneio.hardware.i2c import SMBus2I2C

i2c = SMBus2I2C(bus_number=2)
mcp = MCP23017(i2c=i2c, address=0x20)
pin = mcp.get_pin(0)
pin.switch_to_output(value=False)
```

## Backward Compatibility

Stary kod z importem `from adafruit_mcp230xx.mcp23017 import MCP23017` przestanie działać.
Należy zaktualizować do `from boneio.hardware.gpio.expanders import MCP23017`.

## Następne kroki

1. ✅ **MCP23017** - DONE
2. ⏳ **PCF8575** - GPIO expander 16-pin
3. ⏳ **PCA9685** - PWM driver 16-channel
4. ⏳ Usunięcie pozostałych zależności Adafruit:
   - `adafruit-circuitpython-pca9685`
   - `adafruit-circuitpython-pcf8575`
   - `adafruit-circuitpython-typing`
