# Nowe funkcje do udokumentowania

Rejestr nowych/zmienionych funkcji w boneIO Black do późniejszej dokumentacji.
Status: `[ ]` nie udokumentowane, `[x]` udokumentowane.

---

## Cover

### [ ] Usunięcie platformy `previous` (v1.2.0dev21)
Platforma `previous` została usunięta. Pozostały tylko `time_based` i `venetian`.
Jeśli w konfiguracji była `previous`, po aktualizacji zostanie automatycznie zmieniona na `time_based`.

### [ ] Reload relay cover bez restartu (v1.2.0dev21)
Zmiana `open_relay` / `close_relay` w konfiguracji covera jest stosowana po zapisie bez restartu aplikacji.
Wcześniej zmiana relay wymagała pełnego restartu.

### [ ] Usuwanie covera po reload bez restartu (v1.2.0dev22)
Usunięcie covera z konfiguracji i zapisanie powoduje natychmiastowe usunięcie covera z listy.
Wcześniej usunięty cover był widoczny do restartu aplikacji.

### [ ] SMART_TOGGLE — inteligentny toggle z progiem (planowane v1.2.0dev23)
Nowa akcja cover `SMART_TOGGLE` z parametrem `always_open_till` (próg %).
- Jeśli cover się rusza → STOP
- Jeśli pozycja ≤ próg → OPEN (do 100%)
- Jeśli pozycja > próg → normalne TOGGLE

```yaml
# Przykład konfiguracji
actions:
  double_press:
    - action: cover
      boneio_cover: kitchen_cover
      action_cover: SMART_TOGGLE
      data:
        always_open_till: 40
```

### [ ] ESPHome cover TOGGLE / TOGGLE_OPEN / TOGGLE_CLOSE
TOGGLE na ESPHome cover teraz poprawnie zatrzymuje ruszający się cover lub przełącza kierunek
na podstawie `last_known_operation`. Dodano też `TOGGLE_OPEN` i `TOGGLE_CLOSE`.

---

## Inputs / Events

### [ ] Long press MQTT mode `single`
Tryb `single` dla long press MQTT — wysyła tylko pierwszy event long press na cykl naciśnięcia.
Zapobiega wielokrotnemu triggerowaniu akcji w Node-RED / HA automation.

```yaml
binary_sensor:
  - id: button_1
    pin: P8_12
    long_press_mqtt_mode: single  # domyślnie: all
```

### [ ] Repeat na long press
Akcja z `repeat: true` jest powtarzana cyklicznie podczas trzymania przycisku.
Parametr `repeat_interval` kontroluje minimalny odstęp (domyślnie 800ms).

```yaml
actions:
  long:
    - action: remote_output
      remote_device: salon_esp
      output_id: ceiling_light
      action_output: BRIGHTNESS_UP
      repeat: true
      repeat_interval: 500ms
```

### [ ] Duration thresholds na long press
Akcje long press mogą mieć `min_duration` / `max_duration` — wykonują się tylko
gdy czas trzymania mieści się w podanym zakresie.

---

## Templates

### [ ] Gate cover (template platform)
Nowa platforma template `gate_cover` — brama/garaż sterowana pulsem relay + czujnik kontaktronowy.
Tryby: `cycle`, `separate`, `open_only`. Obsługuje `closed_sensor` i `opened_sensor`.

```yaml
template:
  - id: garage_gate
    platform: gate_cover
    control_mode: cycle
    pulse_output: OUT_01
    pulse_duration: 500ms
    closed_sensor: gate_contact
```

---

## Remote Devices

### [ ] Remote devices — ESPHome API + BoneIO MQTT
Sterowanie urządzeniami zdalnymi (outputy, covery, światła) przez natywne ESPHome API
lub BoneIO MQTT autodiscovery. Akcje: `remote_output`, `remote_cover`.

```yaml
remote_devices:
  - id: salon_esp
    platform: esphome
    host: 192.168.1.50

  - id: garage_boneio
    platform: boneio
```

### [ ] ESPHome light actions (BRIGHTNESS_UP/DOWN, CYCLE_COLOR, CYCLE_PRESET)
Rozszerzone akcje dla świateł ESPHome: płynna regulacja jasności, cykliczne kolory RGB,
cykliczne efekty/presety.

---

## OLED Display

### [ ] Shutdown systemu z przycisku OLED (v1.2.0dev23)
Przycisk OLED obsługuje teraz zamykanie systemu przez long press:
1. Pierwszy long press → ekran potwierdzenia "Shutdown system? Hold button 5s to confirm"
2. Drugi long press (trzymany 5s) → progress bar wypełnia się, po 100% wykonuje `sudo shutdown -h now`
3. Kliknięcie single lub brak akcji przez 10s → anulowanie

Nie wymaga konfiguracji — działa automatycznie na każdym urządzeniu z OLED.

---

## CAN bus

### [ ] CANopen — komunikacja między urządzeniami boneIO przez CAN bus (v1.2.1dev)
Integracja CANopen pozwala na komunikację między urządzeniami boneIO Black przez magistralę CAN.
Tryb **master** — urządzenie z LAN/MQTT przekazuje dane slave'ów do Home Assistant.
Tryb **slave** — urządzenie bez LAN, wysyła dane tylko przez CAN (nie wymaga MQTT).

Funkcje:
- Automatyczne wykrywanie węzłów (autodiscovery przez heartbeat)
- RPDO1 — zdalne sterowanie wyjściami slave'a (ON/OFF/TOGGLE/brightness)
- TPDO1 — raportowanie stanu wyjść do mastera
- CANMQTTBridge — relay stanów CAN↔MQTT w trybie master
- Auto-setup interfejsu CAN (`sudo ip link set`)
- Auto-restart przy błędzie bus-off
- Deterministyczny node_id z adresu MAC (lub ręczny 1-127)

```yaml
# Przykład konfiguracji (master)
can:
  enabled: true
  channel: can0
  bitrate: 125000
  node_id: auto
  mode: master
  auto_setup: true
  restart_on_error: true
```

```yaml
# Przykład konfiguracji (slave — bez MQTT)
can:
  enabled: true
  channel: can0
  bitrate: 125000
  node_id: auto
  mode: slave
```

Wymagania:
- Overlay CAN w `/boot/uEnv.txt`: `uboot_overlay_addr4=/lib/firmware/BB-CAN1-00A0.dtbo`
- Sudoers NOPASSWD dla `ip link set can*`
- Pakiet Python: `python-can`

## WebUI

### [ ] LogViewer — fix kopiowania do schowka
Naprawiono problem gdzie auto-refresh czyścił zaznaczenie logów, uniemożliwiając kopiowanie.

### [ ] BoneIO autodiscovery (send/receive)
Urządzenia BoneIO automatycznie publikują swoje outputy, covery, inputy i sensory
do MQTT discovery topics, umożliwiając wzajemne wykrywanie się urządzeń.
