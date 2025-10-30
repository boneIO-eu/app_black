# Optymalizacja czasu ładowania BoneIO - Lazy Loading

## Analiza profilu importów

**Całkowity czas ładowania: ~8.8 sekund**

### 🐌 TOP 5 najwolniejszych importów:

| Moduł | Czas (s) | % całości | Problem |
|-------|----------|-----------|---------|
| **boneio.webui.app** | 4.04s | 45% | FastAPI + Pydantic ładowane zawsze |
| **boneio.core.config.loader** | 2.71s | 30% | Ładuje wszystkie komponenty |
| **boneio.modbus** | 0.35s | 4% | Pymodbus ładowany zawsze |
| **boneio.hardware.display.oled** | 0.54s | 6% | PIL + qrcode + luma.oled |
| **pydantic** | 1.53s | 17% | Używane przez FastAPI |

### 📋 Szczegółowa analiza:

#### 1. **boneio.webui.app (4.0s)**
```
fastapi: 2.8s
  ├─ fastapi.openapi.models: 2.3s
  ├─ pydantic: 1.5s
  │   ├─ pydantic_core: 0.3s
  │   ├─ typing_extensions: 0.03s
  │   └─ annotated_types: 0.12s
  ├─ starlette: 0.3s
  └─ jose.jwt: 0.77s
```

**Problem:** WebUI jest importowane w `runner.py` nawet jeśli nie jest używane!

#### 2. **boneio.core.config.loader (2.7s)**
```
Ładuje wszystkie komponenty:
  ├─ boneio.components.input: 1.7s
  ├─ boneio.components.sensor: 0.5s
  ├─ boneio.modbus: 0.35s
  └─ boneio.hardware.*: 0.2s
```

**Problem:** Wszystkie komponenty ładowane na starcie, nawet jeśli nie są w konfiguracji!

#### 3. **boneio.hardware.display.oled (0.54s)**
```
  ├─ qrcode: 0.32s
  │   └─ PIL: 0.19s
  └─ luma.oled: 0.17s
```

**Problem:** OLED importy są na górze pliku, ładowane zawsze!

#### 4. **boneio.modbus (0.35s)**
```
  ├─ pymodbus: 0.27s
  │   ├─ pymodbus.pdu: 0.14s
  │   └─ pymodbus.framer: 0.15s
  └─ serial: 0.02s
```

**Problem:** Modbus ładowany w `bonecli.py` nawet dla komendy `run`!

---

## 🚀 Strategia optymalizacji

### Priorytet 1: Lazy load WebUI (oszczędność: ~4s)

**Problem:** WebUI ładowane zawsze w `runner.py`

**Rozwiązanie:**
```python
# runner.py - PRZED
from boneio.webui.web_server import WebServer

# runner.py - PO
def _lazy_import_webserver():
    from boneio.webui.web_server import WebServer
    return WebServer

# Użycie
if web_config:
    WebServer = _lazy_import_webserver()
    web_server = WebServer(...)
```

### Priorytet 2: Lazy load komponentów w config.loader (oszczędność: ~2s)

**Problem:** Wszystkie komponenty ładowane na starcie

**Rozwiązanie:**
```python
# config/loader.py - PRZED
from boneio.components.input.binary_sensor import BinarySensor
from boneio.components.input.event import EventSensor
from boneio.components.sensor.system import SystemSensor
from boneio.modbus.coordinator import ModbusCoordinator

# config/loader.py - PO
def _lazy_import_binary_sensor():
    from boneio.components.input.binary_sensor import BinarySensor
    return BinarySensor

def configure_binary_sensor(...):
    BinarySensor = _lazy_import_binary_sensor()
    return BinarySensor(...)
```

### Priorytet 3: Lazy load OLED dependencies (oszczędność: ~0.5s)

**Problem:** PIL, qrcode, luma.oled importowane na górze pliku

**Rozwiązanie:**
```python
# hardware/display/oled.py - PRZED
from luma.oled.device import sh1106
from qrcode import QRCode
from PIL import Image, ImageDraw, ImageFont

# hardware/display/oled.py - PO
class Oled:
    def __init__(...):
        # Lazy import tylko gdy OLED jest używany
        from luma.oled.device import sh1106
        self._device = sh1106(...)
    
    def _draw_qr_code(self, url: str):
        # Lazy import tylko gdy QR code jest rysowany
        from qrcode import QRCode
        qr = QRCode(...)
```

### Priorytet 4: Lazy load Modbus w CLI (oszczędność: ~0.35s)

**Problem:** Modbus importy w `bonecli.py` dla wszystkich komend

**Rozwiązanie:**
```python
# bonecli.py - PRZED
from boneio.modbus.cli import (
    async_run_modbus_get,
    async_run_modbus_search,
    async_run_modbus_set,
)

# bonecli.py - PO
def main():
    args = get_arguments()
    
    if args.action == "modbus-get":
        from boneio.modbus.cli import async_run_modbus_get
        asyncio.run(async_run_modbus_get(...))
    elif args.action == "run":
        # Nie ładuj modbus dla komendy run
        asyncio.run(async_run(...))
```

---

## 📝 Plan implementacji

### Etap 1: Quick wins (oszczędność: ~4.5s)

1. ✅ **Lazy load WebUI w runner.py**
   - Plik: `boneio/runner.py`
   - Zmiana: Import WebServer tylko gdy `web` w konfiguracji
   - Oszczędność: ~4s

2. ✅ **Lazy load Modbus w bonecli.py**
   - Plik: `boneio/bonecli.py`
   - Zmiana: Import modbus CLI tylko dla komend modbus-*
   - Oszczędność: ~0.35s

3. ✅ **Lazy load OLED dependencies**
   - Plik: `boneio/hardware/display/oled.py`
   - Zmiana: Import luma/qrcode/PIL w metodach
   - Oszczędność: ~0.5s (jeśli OLED nie używany)

### Etap 2: Lazy load komponentów (oszczędność: ~2s)

4. ⏳ **Lazy load w config.loader**
   - Plik: `boneio/core/config/loader.py`
   - Zmiana: Import komponentów w funkcjach configure_*
   - Oszczędność: ~2s

### Etap 3: Optymalizacja FastAPI (oszczędność: ~1s)

5. ⏳ **Lazy load FastAPI routes**
   - Plik: `boneio/webui/app.py`
   - Zmiana: Lazy import dla rzadko używanych endpointów
   - Oszczędność: ~0.5-1s

---

## 🎯 Oczekiwane rezultaty

| Etap | Oszczędność | Czas ładowania |
|------|-------------|----------------|
| **Przed** | - | **15s** |
| Po Etapie 1 | -4.5s | **10.5s** |
| Po Etapie 2 | -6.5s | **8.5s** |
| Po Etapie 3 | -7.5s | **7.5s** |

**Cel: Czas ładowania < 8 sekund** ✅

---

## 🔧 Dodatkowe optymalizacje

### A. Conditional imports w __init__.py

Wiele modułów importuje wszystko w `__init__.py`:

```python
# PRZED - boneio/components/input/__init__.py
from boneio.components.input.binary_sensor import BinarySensor
from boneio.components.input.event import EventSensor

# PO - lazy exports
def __getattr__(name):
    if name == "BinarySensor":
        from boneio.components.input.binary_sensor import BinarySensor
        return BinarySensor
    elif name == "EventSensor":
        from boneio.components.input.event import EventSensor
        return EventSensor
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
```

### B. Defer heavy imports

```python
# Zamiast importować na górze:
import pydantic  # 1.5s

# Import tylko gdy potrzebny:
if TYPE_CHECKING:
    import pydantic

def validate_config(data):
    import pydantic  # Lazy load
    return pydantic.validate(...)
```

### C. Cache importów

```python
_WEBSERVER_CLASS = None

def get_webserver_class():
    global _WEBSERVER_CLASS
    if _WEBSERVER_CLASS is None:
        from boneio.webui.web_server import WebServer
        _WEBSERVER_CLASS = WebServer
    return _WEBSERVER_CLASS
```

---

## 📊 Monitoring

Aby monitorować postęp:

```bash
# Przed zmianami
PYTHONPROFILEIMPORTTIME=1 boneio run -c config.yaml 2>&1 | grep "import time:" | tail -1

# Po każdej zmianie
time boneio run -c config.yaml --help
```

---

## ⚠️ Uwagi

1. **TYPE_CHECKING:** Używaj `if TYPE_CHECKING:` dla type hints
2. **Backward compatibility:** Lazy loading nie zmienia API
3. **Error handling:** Lazy imports mogą rzucać ImportError później
4. **Testing:** Testuj wszystkie ścieżki kodu po zmianach

---

## 🎯 Priorytetowa kolejność implementacji

1. **WebUI lazy load** (4s) - największy impact
2. **Modbus CLI lazy load** (0.35s) - łatwe do zrobienia
3. **OLED lazy load** (0.5s) - średnia trudność
4. **Config loader lazy load** (2s) - wymaga refaktoryzacji
5. **FastAPI optimization** (1s) - zaawansowane

**Łączna oszczędność: ~7.5s (50% czasu ładowania!)**
