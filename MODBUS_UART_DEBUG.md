# Modbus UART Debug Guide

## Problem

```
2025-10-30 08:52:48 ERROR (modbus_worker_0) [pymodbus.logging] Could not configure port: (5, 'Input/output error')
2025-10-30 08:52:48 ERROR (modbus_worker_0) [boneio.modbus.client] Failed to connect Modbus client
2025-10-30 08:52:49 ERROR (modbus_worker_0) [boneio.modbus.client] Can't connect to Modbus.
```

**Errno 5 = Input/output error** - port `/dev/ttyS4` nie może być otwarty.

## Diagnostyka

### 1. Sprawdź czy port istnieje

```bash
ls -la /dev/ttyS*
```

**Oczekiwany output:**
```
crw-rw---- 1 root dialout 4, 68 Oct 30 08:52 /dev/ttyS4
```

**Jeśli nie ma `/dev/ttyS4`:**
- UART4 nie jest włączony w device tree
- Potrzebujesz włączyć UART4 overlay

### 2. Sprawdź uprawnienia

```bash
# Sprawdź grupę użytkownika
groups

# Dodaj użytkownika do grupy dialout
sudo usermod -a -G dialout $USER

# Wyloguj się i zaloguj ponownie
```

### 3. Sprawdź czy port nie jest zajęty

```bash
# Sprawdź procesy używające portu
sudo lsof /dev/ttyS4

# Lub
sudo fuser /dev/ttyS4
```

**Jeśli port jest zajęty:**
```bash
# Zabij proces
sudo pkill -9 -f ttyS4

# Lub konkretny PID
sudo kill -9 <PID>
```

### 4. Sprawdź device tree overlays

```bash
# Na BeagleBone
cat /boot/uEnv.txt | grep uart

# Powinno być coś jak:
# uboot_overlay_addr4=BB-UART4-00A0.dtbo
```

**Jeśli UART4 nie jest włączony:**
```bash
# Edytuj /boot/uEnv.txt
sudo nano /boot/uEnv.txt

# Dodaj linię:
uboot_overlay_addr4=BB-UART4-00A0.dtbo

# Zapisz i zrestartuj
sudo reboot
```

### 5. Test portu manualnie

```bash
# Zainstaluj minicom
sudo apt-get install minicom

# Test portu
sudo minicom -D /dev/ttyS4 -b 9600

# Jeśli działa - port jest OK
# Ctrl+A, X - wyjście
```

### 6. Sprawdź pinmux

```bash
# Sprawdź czy piny są skonfigurowane jako UART
cat /sys/kernel/debug/pinctrl/44e10800.pinmux-pinctrl-single/pinmux-pins | grep -i uart4

# Oczekiwany output:
# pin 70 (PIN70): uart4 (GPIO UNCLAIMED) function uart4 group pinmux_uart4_pins
```

## Rozwiązania

### Rozwiązanie 1: Włącz UART4 w device tree

```bash
sudo nano /boot/uEnv.txt
```

Dodaj/odkomentuj:
```
###Additional custom capes
uboot_overlay_addr4=BB-UART4-00A0.dtbo
```

Zapisz i zrestartuj:
```bash
sudo reboot
```

### Rozwiązanie 2: Uprawnienia

```bash
# Dodaj użytkownika do grupy dialout
sudo usermod -a -G dialout $USER

# Lub zmień uprawnienia portu (tymczasowo)
sudo chmod 666 /dev/ttyS4
```

### Rozwiązanie 3: Zabij konkurujące procesy

```bash
# Znajdź procesy
sudo lsof /dev/ttyS4

# Zabij wszystkie procesy boneio
sudo pkill -9 -f boneio

# Lub konkretny proces
sudo kill -9 <PID>
```

### Rozwiązanie 4: Użyj innego portu UART

Jeśli UART4 nie działa, spróbuj innego:

**Dostępne UART na BeagleBone Black:**
- `/dev/ttyS0` - UART0 (konsola debug - **NIE UŻYWAJ**)
- `/dev/ttyS1` - UART1 (P9.24, P9.26)
- `/dev/ttyS2` - UART2 (P9.21, P9.22)
- `/dev/ttyS4` - UART4 (P9.11, P9.13)
- `/dev/ttyS5` - UART5 (P8.37, P8.38)

**W konfiguracji zmień:**
```yaml
modbus:
  uart:
    id: /dev/ttyS2  # Zamiast /dev/ttyS4
    tx: P9.21
    rx: P9.22
  baudrate: 9600
```

## Dodatkowe logi dla debugowania

Dodaj więcej logów w `boneio/modbus/client.py`:

```python
def _pymodbus_connect(self) -> bool:
    """Connect to Modbus device."""
    try:
        if not self._client:
            _LOGGER.error("Modbus client not initialized")
            return False
        
        # Dodaj debug
        _LOGGER.debug(f"Attempting to connect to port: {self._uart[ID]}")
        _LOGGER.debug(f"Client state before connect: connected={self._client.connected}")
        
        # Check if already connected
        if self._client.connected:
            return True
        
        # Try to connect
        result = self._client.connect()
        
        # Dodaj debug
        _LOGGER.debug(f"Connect result: {result}")
        _LOGGER.debug(f"Client state after connect: connected={self._client.connected}")
        
        if result:
            _LOGGER.debug("Modbus client connected successfully")
            return True
        else:
            _LOGGER.error("Failed to connect Modbus client")
            return False
            
    except Exception as e:
        _LOGGER.error(f"Exception during Modbus connect: {type(e).__name__}: {e}")
        import traceback
        _LOGGER.error(f"Traceback: {traceback.format_exc()}")
        return False
```

## Sprawdź konfigurację hardware

### Pin mapping dla UART4:

| Pin | Funkcja | BeagleBone |
|-----|---------|------------|
| P9.11 | RX | UART4_RXD |
| P9.13 | TX | UART4_TXD |

**Upewnij się że:**
1. Kable są podłączone poprawnie (TX → RX, RX → TX na urządzeniu Modbus)
2. Ground (GND) jest wspólny
3. Napięcie jest kompatybilne (3.3V na BeagleBone)

## Quick Fix - Restart wszystkiego

```bash
# 1. Zatrzymaj wszystkie procesy boneio
sudo pkill -9 -f boneio

# 2. Sprawdź czy port jest wolny
sudo lsof /dev/ttyS4

# 3. Jeśli zajęty - zabij proces
sudo fuser -k /dev/ttyS4

# 4. Uruchom ponownie
boneio run -c /path/to/config.yaml
```

## Weryfikacja działania

Po naprawie powinieneś zobaczyć:
```
2025-10-30 08:52:48 DEBUG Setting UART for modbus communication: {...}
2025-10-30 08:52:48 DEBUG Modbus client connected successfully
2025-10-30 08:52:48 DEBUG Reading registers from...
```

Zamiast:
```
2025-10-30 08:52:48 ERROR Could not configure port: (5, 'Input/output error')
```
