# Python 3.13 I2C Migration Guide

## Problem

**Adafruit Blinka** nie działa na Python 3.13 z BeagleBone Black, ponieważ:
- Wymaga biblioteki `Adafruit_BBIO`
- `Adafruit_BBIO` nie wspiera Python 3.13 (max Python 3.11)
- Projekt jest praktycznie porzucony (ostatni commit 2023)

Błąd który się pojawia:
```
RuntimeError: The library 'Adafruit_BBIO' was not found. 
To install, try typing: pip install Adafruit_BBIO
```

## Rozwiązanie

**Całkowite usunięcie Adafruit Blinka** i przełączenie na **smbus2** z wrapperem kompatybilnym z API Adafruit CircuitPython.

Na Debian 13 zawsze mamy Python 3.13, więc nie ma sensu próbować ładować Blinka.

### Zmiany w kodzie

#### 1. Nowy moduł: `boneio/helper/i2c_wrapper.py`

Wrapper `SMBus2I2CWrapper` który implementuje API `busio.I2C` używając `smbus2`.

**Główne metody:**
- `try_lock()` / `unlock()` - zarządzanie dostępem do magistrali
- `readfrom_into()` - czytanie z urządzenia I2C
- `writeto()` - zapis do urządzenia I2C
- `writeto_then_readfrom()` - zapis + odczyt
- `scan()` - skanowanie magistrali I2C

#### 2. Zmodyfikowane pliki

**`boneio/manager.py`:**
```python
# Usunięto całkowicie import z board/busio
# Bezpośrednio używamy SMBus2I2CWrapper

from boneio.helper.i2c_wrapper import SMBus2I2CWrapper
self._i2cbusio = SMBus2I2CWrapper(bus_number=2)
```

**`boneio/helper/loader.py`:**
```python
# Bezpośredni import smbus2 wrapper
from boneio.helper.i2c_wrapper import SMBus2I2CWrapper as I2C
```

**`boneio/helper/pcf8575.py`:**
```python
# Bezpośredni import smbus2 wrapper
from boneio.helper.i2c_wrapper import SMBus2I2CWrapper as I2C
```

### Brak kompatybilności wstecznej

**Kod jest dedykowany dla Python 3.13+ na Debian 13.**

Adafruit Blinka został całkowicie usunięty, ponieważ:
- ❌ Nie działa na Python 3.13
- ❌ Debian 13 zawsze ma Python 3.13
- ✅ smbus2 jest szybszy i lżejszy

### Testowanie

#### Test 1: Sprawdzenie I2C
```python
from boneio.helper.i2c_wrapper import SMBus2I2CWrapper

# Inicjalizacja
i2c = SMBus2I2CWrapper(bus_number=2)

# Skanowanie urządzeń
devices = i2c.scan()
print(f"Found devices: {[hex(addr) for addr in devices]}")
```

#### Test 2: MCP23017
```python
from adafruit_mcp230xx.mcp23017 import MCP23017
from boneio.helper.i2c_wrapper import SMBus2I2CWrapper

i2c = SMBus2I2CWrapper(bus_number=2)
mcp = MCP23017(i2c=i2c, address=0x20, reset=False)

# Test pinu
pin = mcp.get_pin(0)
pin.direction = digitalio.Direction.OUTPUT
pin.value = True
```

### Konfiguracja I2C na BeagleBone Black

Domyślnie używany jest **I2C-2** (bus_number=2).

Sprawdzenie dostępnych magistrali:
```bash
ls /dev/i2c-*
```

Skanowanie urządzeń:
```bash
i2cdetect -y -r 2
```

### Zależności

W `pyproject.toml` już masz:
```toml
dependencies = [
    "smbus2==0.4.3",  # ✅ Wymagane dla Python 3.13
    "adafruit-circuitpython-mcp230xx==2.5.18",
    "adafruit-circuitpython-pca9685==3.4.19",
    "adafruit-circuitpython-pcf8575==1.0.11",
]
```

### Wydajność

**smbus2 vs Blinka:**
- ⚡ **smbus2 jest szybszy** - brak warstwy abstrakcji Blinka
- 📦 **Lżejszy** - mniej zależności
- 🔧 **Bezpośredni dostęp** do kernela Linux

### Znane ograniczenia

1. **Częstotliwość I2C**: `smbus2` nie pozwala na zmianę częstotliwości w runtime
   - Domyślnie: 100 kHz
   - Można zmienić w device tree

2. **Timeout**: `smbus2` używa domyślnych timeoutów kernela
   - Można dostosować przez `/sys/bus/i2c/devices/i2c-2/timeout`

### Troubleshooting

#### Problem: "Permission denied" na `/dev/i2c-2`
```bash
# Dodaj użytkownika do grupy i2c
sudo usermod -a -G i2c $USER
# Lub ustaw uprawnienia
sudo chmod 666 /dev/i2c-2
```

#### Problem: "No such file or directory: '/dev/i2c-2'"
```bash
# Sprawdź czy I2C jest włączone w device tree
ls /dev/i2c-*

# Włącz I2C-2 w uEnv.txt lub device tree overlay
```

#### Problem: Urządzenie nie odpowiada
```bash
# Sprawdź czy urządzenie jest widoczne
i2cdetect -y -r 2

# Sprawdź logi kernela
dmesg | grep i2c
```

## Podsumowanie

✅ **Kod jest gotowy na Python 3.13**
✅ **Usunięto Adafruit Blinka** - nie jest potrzebny
✅ **Lepsza wydajność** dzięki bezpośredniemu smbus2
✅ **Mniej zależności** - nie potrzeba Adafruit_BBIO ani Blinka
✅ **Prostszy kod** - bez warunków try/except dla Blinka

**Wymagania:**
- Python 3.13+
- Debian 13
- smbus2==0.4.3
- Biblioteki Adafruit CircuitPython (MCP23017, PCA9685, PCF8575)
