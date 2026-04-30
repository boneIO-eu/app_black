# boneIO Black v1.3.0 🎉

---

## 🇬🇧 English

Spring release — packed with new features, protocol support, and a complete WebUI overhaul!

### ✨ New Features

- 🌿 **Multi-zone irrigation controller** — schedules, per-zone intervals, water source management, master valve support, and a full dashboard UI with real-time zone countdown. All controlled also from Home Assistant!
- 🎛️ **Conditional actions** — time ranges, date ranges, and entity state conditions with AND/OR logic. Actions fire only when conditions are met
- 🎛️ **Each output now has individual action capabilities** — fine-grained control over what each output can do
- 📊 **Live graphs** added to the WebUI dashboard for real-time data visualization
- 📊 **Simple history view** for sensors — see past values at a glance
- ⏱️ **Timed output with HA input** — change the timer value directly from Home Assistant, no YAML restart needed
- 🔌 **LoxUDP protocol** — initial integration for Lox UDP communication
- 🔌 **CANOpen protocol** — initial support for CAN bus industrial devices
- 🏠 **Experimental `ha_child_devices` mode** for HA discovery — organize entities as child devices
- 🏠 **Output groups visible in HA** — output groups are now exposed to Home Assistant with their member outputs, so you can see which outputs belong to each group
- 🏠 **Entity category reorganization** — entities moved into proper HA categories (diagnostic, config) for a cleaner HA UI
- 🏠 **Republish states on MQTT autodiscovery resend** — ensures HA always has the latest state after reconnects
- 🔧 **48×4A legacy board support** — added device type for older 48-output / 4A boards
- 🔧 **Tilt support for remote devices** — venetian blinds on remote boneIO devices now support tilt actions
- 📦 **Modbus entity naming** — custom entity names for Modbus devices
- 📦 **Temperature sensor rounding** — configurable decimal rounding for temperature readings
- 📦 **Serial number in backup filenames** — easier identification of backup files across multiple devices

### 🐛 Bug Fixes

- **OLED refresh interval** — fixed display refresh timing causing stale or flickering content
- **Modbus WebUI loading time** — significantly reduced initial load time of Modbus device view
- **Modbus communication isolation** — other Modbus traffic is now blocked while using WebUI tools, preventing bus conflicts

### ♻️ UI / UX Improvements

- **Hundreds of UI fixes** across the entire WebUI — padding consistency, card styling, shadow standardization, responsive layout improvements
- **System Settings overhaul** — redesigned Current Version, Available Versions, App Permissions, CAN Permissions, and Migrations sections
- **Migrations table** — professional table layout with descriptions, status badges, and GitHub source links

---

## 🇵🇱 Polski

Wiosenne wydanie — pełne nowych funkcji, wsparcia protokołów i kompletnej przebudowy WebUI!

### ✨ Nowe Funkcje

- 🌿 **Wielostrefowy kontroler nawadniania** — harmonogramy, interwały per strefa, zarządzanie źródłami wody, zawór główny i pełny panel UI z odliczaniem czasu na żywo. Wszystko sterowane również z Home Assistant!
- 🎛️ **Akcje warunkowe** — zakresy czasowe, zakresy dat i warunki stanu encji z logiką AND/OR. Akcje wykonują się tylko gdy warunki są spełnione
- 🎛️ **Każde wyjście ma teraz indywidualne możliwości akcji** — precyzyjna kontrola nad tym, co każde wyjście może robić
- 📊 **Wykresy na żywo** dodane do dashboardu WebUI do wizualizacji danych w czasie rzeczywistym
- 📊 **Prosty widok historii** dla sensorów — podgląd poprzednich wartości
- ⏱️ **Wyjście czasowe z inputem HA** — zmiana wartości timera bezpośrednio z Home Assistant, bez restartu
- 🔌 **Protokół LoxUDP** — wstępna integracja komunikacji Lox UDP
- 🔌 **Protokół CANOpen** — wstępne wsparcie dla urządzeń przemysłowych CAN bus
- 🏠 **Eksperymentalny tryb `ha_child_devices`** dla HA discovery — organizacja encji jako urządzenia podrzędne
- 🏠 **Grupy wyjść widoczne w HA** — grupy wyjść są teraz eksponowane w Home Assistant wraz z przynależnymi wyjściami
- 🏠 **Reorganizacja kategorii encji** — encje przeniesione do odpowiednich kategorii HA (diagnostic, config) dla czytelniejszego UI
- 🏠 **Ponowne publikowanie stanów przy autodiscovery** — HA zawsze ma najnowszy stan po ponownym połączeniu
- 🔧 **Wsparcie płytek 48×4A** — dodano typ urządzenia dla starszych płytek 48-wyjściowych / 4A
- 🔧 **Wsparcie tilt dla zdalnych urządzeń** — rolety weneckie na zdalnych boneIO obsługują teraz akcje tilt
- 📦 **Nazwy encji Modbus** — własne nazwy encji dla urządzeń Modbus
- 📦 **Zaokrąglanie sensorów temperatury** — konfigurowalne zaokrąglanie miejsc dziesiętnych
- 📦 **Numer seryjny w nazwach kopii zapasowych** — łatwiejsza identyfikacja plików backup z wielu urządzeń

### 🐛 Poprawki Błędów

- **Interwał odświeżania OLED** — naprawiono timing odświeżania wyświetlacza
- **Czas ładowania Modbus w WebUI** — znacząco skrócono czas początkowego ładowania widoku
- **Izolacja komunikacji Modbus** — ruch Modbus jest blokowany podczas korzystania z narzędzi WebUI

### ♻️ Ulepszenia Interfejsu

- **Setki poprawek UI** w całym WebUI — spójność paddingu, stylowanie kart, standaryzacja cieni, responsywny layout
- **Przebudowa Ustawień Systemu** — przeprojektowane sekcje Obecna Wersja, Dostępne Wersje, Uprawnienia Aplikacji, Uprawnienia CAN i Migracje
- **Tabela migracji** — profesjonalny layout tabelaryczny z opisami, badge'ami statusu i linkami do źródeł na GitHubie

---

**Full Changelog / Pełny changelog**: https://github.com/boneIO-eu/app_black/compare/v1.2.0...v1.3.0
