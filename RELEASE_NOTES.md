# boneIO Black v1.3.1

---

## 🇬🇧 English

Maintenance release focused on stability, type safety, and Home Assistant integration improvements.

### ✨ New Features

- 🔧 **Support for legacy 0.2 / 0.3 boards** — added device definitions for older boneIO Black hardware revisions
- 🏠 **HA Update entity changed to binary sensor** — firmware update entity is now a binary sensor for cleaner HA integration

### 🐛 Bug Fixes

- **Cover position precision** — fixed inconsistent float/int conversion in cover position calculations, eliminating rounding drift during movement
- **Cover timestamp tracking** — fixed incorrect timestamps in cover state updates
- **HA discovery device_class** — fixed null device_class in Home Assistant autodiscovery by storing it directly on the input object
- **HA Update entity state during firmware restart** — update entity now correctly shows 'Updating' state during firmware restart instead of going offline
- **Event form click handling** — fixed click event handling in the WebUI event configuration form

### ♻️ Refactoring

- **Unified device_class** — refactored device_class to be a single source of truth on the input object (GpioBaseClass)
- **Removed gpio_mode** — deprecated gpio_mode setting, now handled by kernel overlay
- **Removed CAN System settings** — CAN configuration migrated to system migrations, manual settings no longer needed
- **Type safety improvements** — fixed multiple type checker issues across the codebase (Pyrefly/Pyright compatibility)

### ⚠️ Duplicate Entity Fix in Home Assistant

If you see **duplicated entities** for your boneIO Black device in Home Assistant after updating:

1. Go to Home Assistant → **Settings** → **Devices & Services** → **Devices** tab
2. Enter **Selection Mode**, select the boneIO Black devices with duplicated entities, and **delete** them
3. Open the boneIO controller's WebUI → **Settings** → **Communication Protocols** → **MQTT** tab
4. Click **"Delete and resend HA Discovery"**

This will cleanly re-register all entities without duplicates.

---

## 🇵🇱 Polski

Wydanie serwisowe skupione na stabilności, bezpieczeństwie typów i poprawkach integracji z Home Assistant.

### ✨ Nowe Funkcje

- 🔧 **Wsparcie dla starszych płytek 0.2 / 0.3** — dodano definicje urządzeń dla starszych rewizji sprzętowych boneIO Black
- 🏠 **Encja aktualizacji HA zmieniona na binary sensor** — encja aktualizacji firmware jest teraz czujnikiem binarnym dla czystszej integracji z HA

### 🐛 Poprawki Błędów

- **Precyzja pozycji rolet** — naprawiono niespójną konwersję float/int w obliczeniach pozycji rolet, eliminując dryft zaokrągleń podczas ruchu
- **Znaczniki czasu rolet** — naprawiono nieprawidłowe znaczniki czasu w aktualizacjach stanu rolet
- **device_class w HA discovery** — naprawiono null device_class w autodiscovery Home Assistant poprzez przechowywanie go bezpośrednio na obiekcie wejścia
- **Stan encji aktualizacji podczas restartu firmware** — encja aktualizacji teraz prawidłowo pokazuje stan 'Updating' podczas restartu firmware zamiast znikać
- **Obsługa kliknięć w formularzu zdarzeń** — naprawiono obsługę zdarzeń kliknięcia w formularzu konfiguracji zdarzeń WebUI

### ♻️ Refaktoryzacja

- **Ujednolicony device_class** — refaktoryzacja device_class jako jedynego źródła prawdy na obiekcie wejścia (GpioBaseClass)
- **Usunięto gpio_mode** — ustawienie gpio_mode jest przestarzałe, teraz obsługiwane przez overlay kernela
- **Usunięto ustawienia CAN System** — konfiguracja CAN przeniesiona do migracji systemowych, ręczne ustawienia nie są już potrzebne
- **Poprawki bezpieczeństwa typów** — naprawiono wiele problemów z type checkerami w całym kodzie (kompatybilność Pyrefly/Pyright)

### ⚠️ Naprawa zdublowanych encji w Home Assistant

Jeśli po aktualizacji widzisz **zdublowane encje** urządzenia boneIO Black w Home Assistant:

1. Wejdź w Home Assistant → **Ustawienia** → **Urządzenia i usługi** → zakładka **Urządzenia**
2. Wejdź w **Tryb zaznaczania**, zaznacz urządzenia boneIO Black, które mają zdublowane encje i je **usuń**
3. Otwórz WebUI sterownika → **Ustawienia** → **Protokoły komunikacyjne** → zakładka **MQTT**
4. Wybierz **„Usuń i wyślij ponownie HA Discovery"**

To czysto ponownie zarejestruje wszystkie encje bez duplikatów.

---

**Full Changelog / Pełny changelog**: https://github.com/boneIO-eu/app_black/compare/v1.3.0...v1.3.1
