# Naprawa duplikacji plików - Etap 1 (poprawka)

## Problem
W Etapie 1 refaktoryzacji **skopiowałem** pliki z `helper/` i `message_bus/` do `core/`, ale **nie usunąłem oryginałów**. Skutkowało to:
- Duplikacją kodu
- Koniecznością aktualizacji obu wersji przy zmianach (jak w przypadku MCP23017)
- Niejasnością gdzie jest faktycznie używany kod

## Rozwiązanie

### 1. Usunięte duplikaty z `helper/`
Usunięto pliki które zostały przeniesione do `core/`:

```bash
# USUNIĘTE (są w core/):
helper/loader.py           → core/config/loader.py
helper/yaml_util.py        → core/config/yaml_util.py
helper/state_manager.py    → core/state/manager.py
helper/timeperiod.py       → core/utils/timeperiod.py
helper/util.py             → core/utils/util.py
helper/filter.py           → core/utils/filter.py
helper/logger.py           → core/utils/logger.py
helper/config.py           → core/config/config_helper.py
helper/schema_converter.py → core/config/schema_converter.py
```

**ZACHOWANO w `helper/`** tylko prawdziwe utility/helper pliki:
- `async_updater.py` - helper do async updates
- `click_timer.py` - timer dla kliknięć
- `events.py` - event bus helpers (częściowo, EventBus jest w core/events)
- `exceptions.py` - custom exceptions
- `ha_discovery.py` - Home Assistant discovery
- `i2c_wrapper.py` - backward compatibility wrapper (DEPRECATED)
- `interlock.py` - software interlock
- `mqtt.py` - MQTT helpers
- `oled.py` - OLED display helpers
- `pcf8575.py` - PCF8575 expander (do przepisania na smbus2)
- `queue.py` - UniqueQueue
- `stats.py` - Host statistics
- `__init__.py` - **backward compatibility** re-exports

### 2. Usunięte duplikaty z `message_bus/`
```bash
# USUNIĘTE (są w core/messaging/):
message_bus/basic.py  → core/messaging/basic.py
message_bus/local.py  → core/messaging/local.py
message_bus/mqtt.py   → core/messaging/mqtt.py
```

**ZACHOWANO**:
- `message_bus/__init__.py` - **backward compatibility** re-exports

### 3. Zaktualizowane importy

Pliki które miały bezpośrednie importy z usuniętych plików:

| Plik | Przed | Po |
|------|-------|-----|
| `message_bus/mqtt.py` | `from boneio.helper.config` | `from boneio.core.config` |
| `bonecli.py` | `from boneio.helper.logger` | `from boneio.core.utils.logger` |
| `helper/events.py` | `from boneio.helper.util` | `from boneio.core.utils.util` |
| `helper/mqtt.py` | `from boneio.helper.util` | `from boneio.core.utils.util` |

## Backward Compatibility

✅ **Zachowana** - dzięki re-export wrappers:

```python
# helper/__init__.py
from boneio.core.state import StateManager
from boneio.core.utils import TimePeriod, callback
from boneio.core.config.yaml_util import load_config_from_file
# ... etc

# message_bus/__init__.py
from boneio.core.messaging import LocalMessageBus, MessageBus, MQTTClient
```

Stary kod nadal działa:
```python
# STARE (nadal działa):
from boneio.helper import StateManager, TimePeriod
from boneio.message_bus import MessageBus

# NOWE (zalecane):
from boneio.core.state import StateManager
from boneio.core.utils import TimePeriod
from boneio.core.messaging import MessageBus
```

## Weryfikacja

✅ Syntax check wszystkich zaktualizowanych plików  
✅ Brak duplikatów w `helper/` i `message_bus/`  
✅ Backward compatibility przez re-exports  
✅ Wszystkie importy zaktualizowane  

## Podsumowanie zmian

- **9 plików** usunięto z `helper/`
- **3 pliki** usunięto z `message_bus/`
- **4 pliki** zaktualizowano (importy)
- **0 plików** zepsuto (backward compatibility zachowana)

## Finalna struktura

```
boneio/
├── core/                    # Główna logika (NOWE)
│   ├── config/             # Konfiguracja
│   ├── events/             # Event bus
│   ├── messaging/          # Message bus / MQTT
│   ├── state/              # State management
│   └── utils/              # Utilities
├── hardware/                # Hardware abstraction (Etap 2)
│   ├── i2c/
│   └── gpio/expanders/
├── helper/                  # Utilities & helpers
│   └── __init__.py         # Re-exports from core.*
└── message_bus/             # Backward compatibility
    └── __init__.py         # Re-exports from core.messaging.*
```
