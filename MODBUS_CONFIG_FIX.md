# Fix: Modbus Configuration Error

## Data: 30 października 2025

## Błąd

```
2025-10-30 10:13:04 ERROR (MainThread) [boneio.core.manager.modbus] Failed to configure Modbus: 'str' object has no attribute 'get'
```

## Przyczyna

Konfiguracja `modbus` w `config.yaml` jest **stringiem** zamiast **dict**.

### Nieprawidłowa konfiguracja (powoduje błąd):

```yaml
# ❌ BŁĄD - modbus jako string
modbus: uart4
```

lub

```yaml
# ❌ BŁĄD - modbus jako string z pełną ścieżką
modbus: /dev/ttyS4
```

### Prawidłowa konfiguracja:

```yaml
# ✅ POPRAWNIE - modbus jako dict
modbus:
  uart: uart4
  baudrate: 9600
  stopbits: 1
  bytesize: 8
  parity: 'N'
```

## Rozwiązanie

### 1. Dodano walidację typu w `modbus.py`

**Plik:** `boneio/core/manager/modbus.py`

**Zmiana:**
```python
def _configure_modbus(self, modbus_config: dict[str, Any], ...):
    try:
        from boneio.modbus.client import Modbus
        
        # Validate modbus_config is a dict
        if not isinstance(modbus_config, dict):
            _LOGGER.error(
                "Invalid modbus configuration: expected dict, got %s. "
                "Check your config.yaml - modbus should be a dict with 'uart' key.",
                type(modbus_config).__name__
            )
            return
        
        # Continue with configuration...
        uart = modbus_config.pop(UART)
        ...
```

**Korzyści:**
- Jasny komunikat błędu zamiast cryptycznego `'str' object has no attribute 'get'`
- Wskazuje dokładnie co jest nie tak
- Podpowiada jak naprawić

### 2. Nowy komunikat błędu

**Przed:**
```
ERROR Failed to configure Modbus: 'str' object has no attribute 'get'
```

**Po:**
```
ERROR Invalid modbus configuration: expected dict, got str. 
      Check your config.yaml - modbus should be a dict with 'uart' key.
```

## Jak naprawić konfigurację

### Krok 1: Otwórz `config.yaml`

```bash
nano /path/to/config.yaml
```

### Krok 2: Znajdź sekcję `modbus`

Szukaj linii zaczynającej się od `modbus:`

### Krok 3: Popraw format

**Jeśli masz:**
```yaml
modbus: uart4
```

**Zmień na:**
```yaml
modbus:
  uart: uart4
  baudrate: 9600
```

**Jeśli masz:**
```yaml
modbus: /dev/ttyS4
```

**Zmień na:**
```yaml
modbus:
  uart: uart4  # Użyj nazwy logicznej, nie ścieżki
  baudrate: 9600
```

### Krok 4: Zapisz i zrestartuj

```bash
# Zapisz plik (Ctrl+O, Enter, Ctrl+X w nano)

# Zrestartuj BoneIO
sudo systemctl restart boneio
# lub
boneio run -c /path/to/config.yaml
```

## Pełna konfiguracja Modbus

### Minimalna (tylko wymagane pola):

```yaml
modbus:
  uart: uart4
```

### Pełna (wszystkie opcje):

```yaml
modbus:
  uart: uart4        # Wymagane: uart1, uart2, uart3, uart4, uart5
  baudrate: 9600     # Opcjonalne, domyślnie 9600
  stopbits: 1        # Opcjonalne, domyślnie 1 (dozwolone: 1, 2)
  bytesize: 8        # Opcjonalne, domyślnie 8
  parity: 'N'        # Opcjonalne, domyślnie 'N' (dozwolone: N, E, O)

modbus_devices:
  - id: device1
    address: 1
    # ... konfiguracja urządzenia
```

## Dostępne UART

| UART | Piny BeagleBone | Ścieżka device |
|------|-----------------|----------------|
| uart1 | P9.24, P9.26 | /dev/ttyS1 |
| uart2 | P9.21, P9.22 | /dev/ttyS2 |
| uart4 | P9.11, P9.13 | /dev/ttyS4 |
| uart5 | P8.37, P8.38 | /dev/ttyS5 |

**Uwaga:** Używaj nazwy logicznej (np. `uart4`), nie ścieżki device (np. `/dev/ttyS4`)!

## Weryfikacja konfiguracji

Po poprawieniu, sprawdź logi:

```bash
# Uruchom z debug
boneio run -c /path/to/config.yaml --debug 2

# Szukaj w logach:
# ✅ Poprawnie:
INFO Modbus configured on UART uart4

# ❌ Błąd:
ERROR Invalid modbus configuration: expected dict, got str
```

## Przykład kompletnej konfiguracji

```yaml
boneio:
  device_type: 32_10
  version: 1.0

modbus:
  uart: uart4
  baudrate: 9600
  parity: 'N'

modbus_devices:
  - id: energy_meter
    address: 1
    device_type: sdm120
    update_interval: 10
    registers:
      - name: voltage
        address: 0
        type: input
        data_type: float32
      - name: current
        address: 6
        type: input
        data_type: float32

mqtt:
  host: localhost
  port: 1883
```

## Dodatkowe informacje

- **Schema validation:** Cerberus waliduje że `modbus` musi być `dict`, ale błąd może się pojawić jeśli:
  - Używasz starej wersji schema
  - Ręcznie edytujesz YAML i popełniasz błąd składni
  - Kopiujesz konfigurację z innego źródła

- **YAML syntax:** W YAML, jeśli chcesz dict, musisz użyć wcięcia:
  ```yaml
  # Dict (poprawnie)
  modbus:
    uart: uart4
  
  # String (błąd)
  modbus: uart4
  ```

## Zobacz też

- [MODBUS_UART_DEBUG.md](MODBUS_UART_DEBUG.md) - Diagnostyka problemów z UART
- [check_uart.sh](check_uart.sh) - Skrypt do sprawdzania UART
- [Dokumentacja Modbus](https://boneio.eu/docs/black/configuration/modbus)
