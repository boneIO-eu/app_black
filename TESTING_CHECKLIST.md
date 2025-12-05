# BoneIO Testing Checklist

Lista testów do przeprowadzenia dla aplikacji BoneIO.

## 1. Wyświetlacz OLED

### Testy manualne
- [ ] Wyświetlacz włącza się przy starcie aplikacji
- [ ] Przycisk OLED przełącza ekrany (każdy klik = następny ekran)
- [ ] Wyświetlacz przechodzi w tryb uśpienia po timeout
- [ ] Klik budzi wyświetlacz ze snu (nie przełącza ekranu)
- [ ] Wyświetlanie QR code z adresem WebUI
- [ ] Wyświetlanie stanu relay'ów
- [ ] Wyświetlanie stanu inputów

### Testy jednostkowe
- [ ] `Oled._handle_button_press()` - logika wake/next_screen
- [ ] `Oled.start_sleep_timer()` - timer działa poprawnie
- [ ] `Oled.wake_up()` - anuluje timer i budzi ekran

---

## 2. 1-Wire (DS18B20)

### Testy manualne
- [ ] Wykrywanie czujników temperatury na magistrali
- [ ] Odczyt temperatury z czujnika
- [ ] Aktualizacja temperatury w zadanym interwale
- [ ] Obsługa błędów przy odłączonym czujniku
- [ ] Wysyłanie stanu do MQTT/HA

### Testy jednostkowe
- [ ] Skanowanie magistrali 1-Wire
- [ ] Parsowanie odczytu temperatury
- [ ] Obsługa CRC błędów

---

## 3. Sensory RS485 / Modbus

### Testy manualne
- [ ] Komunikacja z urządzeniem Modbus RTU
- [ ] Odczyt rejestrów holding/input
- [ ] Zapis do rejestrów holding
- [ ] Obsługa timeout przy braku odpowiedzi
- [ ] Obsługa błędów CRC
- [ ] Konfiguracja różnych baud rate (9600, 19200, 115200)

### Testy jednostkowe
- [ ] Budowanie ramek Modbus
- [ ] Parsowanie odpowiedzi
- [ ] Konwersja typów danych (int16, uint16, float32)

### Status testów jednostkowych
- [x] Mock `MockModbusSerialClient` w `tests/mocks/modbus.py`
- [x] Testy odczytu rejestrów w `tests/unit/modbus/test_modbus_client.py`
- [x] Symulacja SDM120 (licznik energii)
- [x] Symulacja CWT (przekładnik prądowy)
- [x] Symulacja timeout i błędów
- [ ] Testy integracyjne z `boneio.modbus.client.Modbus`

---

## 4. ADC (Przetwornik analogowo-cyfrowy)

### Testy manualne
- [ ] Odczyt wartości z kanału ADC
- [ ] Kalibracja odczytu (raw → voltage)
- [ ] Filtrowanie szumów (średnia krocząca)
- [ ] Aktualizacja w zadanym interwale

### Testy jednostkowe
- [ ] Konwersja raw value → napięcie
- [ ] Algorytm filtrowania
- [ ] Obsługa przekroczenia zakresu

---

## 5. MCP23017 / PCF8575 / PCA9685

### Testy manualne
- [ ] Inicjalizacja expandera I2C
- [ ] Ustawienie pinu jako output
- [ ] Włączenie/wyłączenie relay'a
- [ ] Odczyt stanu pinu
- [ ] Obsługa wielu expanderów na jednej magistrali

### Testy jednostkowe
- [ ] `MCP23017.__init__()` - konfiguracja rejestrów
- [ ] `MCP23017.set_pin_value()` - zapis do OLAT
- [ ] `MCP23017.get_pin_value()` - odczyt z GPIO
- [ ] `MCP23017.configure_pin_as_output()` - zapis do IODIR
- [ ] Walidacja numeru pinu (0-15)

### Status testów jednostkowych
- [x] Podstawowe testy w `tests/unit/hardware/test_mcp23017.py`
- [ ] Testy dla PCF8575
- [ ] Testy dla PCA9685 (PWM)

---

## 6. MQTT

### Testy manualne
- [ ] Połączenie z brokerem MQTT
- [ ] Reconnect po utracie połączenia
- [ ] Publikowanie stanu output'ów
- [ ] Publikowanie stanu sensorów
- [ ] Odbieranie komend (turn_on, turn_off, toggle)
- [ ] Home Assistant autodiscovery

### Testy jednostkowe
- [ ] Budowanie topic'ów MQTT
- [ ] Serializacja payload'ów JSON
- [ ] Obsługa QoS
- [ ] Parsowanie komend

---

## 7. Event Entity (przyciski z akcjami)

### Testy manualne
- [ ] Wykrywanie kliknięcia (pressed/released)
- [ ] Wykrywanie double click
- [ ] Wykrywanie long press
- [ ] Wykrywanie triple click
- [ ] Wykonywanie akcji przypisanych do kliknięć
- [ ] Debouncing (bounce_time)

### Testy jednostkowe
- [ ] `MulticlickDetector` - wykrywanie typów kliknięć
- [ ] Timeout między kliknięciami
- [ ] Mapowanie click_type → akcja

### Status testów jednostkowych
- [x] Podstawowe testy w `tests/multiclick_detector.py`

---

## 8. Binary Sensor

### Testy manualne
- [ ] Wykrywanie zmiany stanu (ON/OFF)
- [ ] Wysyłanie stanu do MQTT/HA
- [ ] Debouncing
- [ ] Inverted logic (show_in_ha: false)

### Testy jednostkowe
- [ ] Callback przy zmianie stanu
- [ ] Filtrowanie bounce'ów

---

## 9. Outputs (Relay)

### Testy manualne
- [ ] Włączenie relay'a (turn_on)
- [ ] Wyłączenie relay'a (turn_off)
- [ ] Toggle
- [ ] Momentary mode (pulse)
- [ ] Interlock (wzajemne blokowanie)
- [ ] Restore state po restarcie

### Testy jednostkowe
- [ ] `BasicOutput.turn_on()` / `turn_off()`
- [ ] `BasicOutput.toggle()`
- [ ] Momentary timer
- [ ] Interlock logic

---

## 10. Cover (Rolety)

### Testy manualne
- [ ] Otwieranie rolety
- [ ] Zamykanie rolety
- [ ] Stop w trakcie ruchu
- [ ] Ustawienie pozycji (0-100%)
- [ ] Tilt (jeśli obsługiwany)
- [ ] Kalibracja czasów open/close

### Testy jednostkowe
- [ ] Obliczanie pozycji na podstawie czasu
- [ ] Logika stop
- [ ] Obsługa limitów (0%, 100%)

---

## 11. WebUI / API

### Testy manualne
- [ ] Dostęp do WebUI przez przeglądarkę
- [ ] Wyświetlanie stanu urządzeń
- [ ] Sterowanie relay'ami z WebUI
- [ ] Edycja konfiguracji
- [ ] Restart aplikacji z WebUI

### Testy jednostkowe/integracyjne
- [ ] Endpointy REST API
- [ ] WebSocket events
- [ ] Autentykacja (jeśli włączona)

---

## 12. System / Startup

### Testy manualne
- [ ] Aplikacja startuje bez błędów
- [ ] Ładowanie konfiguracji YAML
- [ ] Graceful shutdown (SIGTERM)
- [ ] Logi bez błędów krytycznych

### Testy jednostkowe
- [ ] Parsowanie konfiguracji
- [ ] Walidacja schema
- [ ] Obsługa brakujących pól (defaults)

---

## Priorytety testów

### Wysoki priorytet (krytyczne dla działania)
1. MCP23017 / PCF8575 - sterowanie relay'ami
2. MQTT - komunikacja z Home Assistant
3. Event Entity - obsługa przycisków
4. Startup / konfiguracja

### Średni priorytet
5. Binary Sensor
6. Outputs (relay logic)
7. Cover
8. 1-Wire / sensory temperatury

### Niski priorytet (nice to have)
9. OLED display
10. ADC
11. WebUI
12. Modbus

---

## Jak uruchomić testy

```bash
# Instalacja zależności testowych
pip3 install pytest pytest-asyncio pytest-cov

# Uruchomienie wszystkich testów
pytest tests/ -v

# Uruchomienie testów z coverage
pytest tests/ --cov=boneio --cov-report=html

# Uruchomienie konkretnego testu
pytest tests/unit/hardware/test_mcp23017.py -v

# Uruchomienie testów z logami
pytest tests/ -v -s --log-cli-level=DEBUG
```

---

## Notatki

- Testy hardware wymagają mocków (patrz `tests/mocks/`)
- Testy integracyjne wymagają rzeczywistego hardware'u
- Przed release'em uruchom pełny zestaw testów manualnych

