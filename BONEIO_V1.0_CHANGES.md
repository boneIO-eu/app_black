# 🛠️ Zmiany dla wersji płytki boneIO Black v1.0

W ramach przystosowania oprogramowania do nowej rewizji płytki **v1.0** (która zastępuje GPIO 1-Wire dedykowanym układem **DS2484** na I2C2 oraz dodaje buzzer na pinie **P9_12**), wprowadzono następujące zmiany:

## 1. Konfiguracja sprzętowa (Boards configuration)
- Utworzono katalog `/boneio/boards/1.0/` zawierający szablony konfiguracyjne identyczne z wersją 0.8.
- Do wszystkich szablonów wyjściowych (`output_*.yaml` w wersji `1.0`) dodano automatyczną definicję mostka 1-Wire:
  ```yaml
  ds2482:
    - id: ds2482_bus
      address: 0x18
  ```
- W mapowaniu wyjść (`output_mapping`) dodano domyślny buzzer:
  ```yaml
  output_mapping:
    buzzer:
      kind: buzzer
      output_type: switch
  ```

## 2. Nowy komponent Buzzer (`BuzzerOutput`)
- Dodano nową klasę wyjściową `BuzzerOutput` w pliku `boneio/components/output/buzzer.py`.
- Klasa steruje buzzerem poprzez sysfs LED driver (`/sys/class/leds/boneio:buzzer/brightness`), ponieważ fizyczny pin `P9_12` jest przejmowany przez sterownik jądra `leds-gpio` w overlayu.
- Klasa dziedziczy z `BasicOutput` i obsługuje pełną integrację z Home Assistant (jako switch/light/led), w tym tryby momentary (impulsowe) oraz adjustable duration (regulowany czas włączenia).

## 3. Autowykrywanie i domyślna platforma 1-Wire
- Zaktualizowano `ConfigHelper` oraz `runner.py`, aby poprawnie wczytywały i przekazywały wersję sprzętową `"1.0"`.
- Zaktualizowano validator schematu `boneio/schema/schema.yaml`, zezwalając na wersję `"1.0"` / `1.0` oraz nowy typ wyjścia `kind: buzzer` wraz z opcjonalnym parametrem `sysfs_path`.
- W klasie `SensorManager` (`boneio/core/manager/sensors.py`) dodano **automatyczne mapowanie platformy dla czujników 1-Wire (Dallas)**. Jeśli użytkownik posiada płytkę w wersji `1.0`, a w pliku konfiguracyjnym nie określił platformy czujnika, system automatycznie ustawi:
  - `platform: ds2482`
  - `bus_id: ds2482_bus`
  Dzięki temu przejście z wersji 0.8 na 1.0 nie wymaga ręcznej edycji każdego czujnika temperatury Dallas w pliku `config.yaml`.

## 4. Testy jednostkowe
- Utworzono zestaw testów jednostkowych w `tests/unit/hardware/test_buzzer.py`, które weryfikują:
  - Prawidłową inicjalizację stanu buzzera (z uwzględnieniem przywracania stanu).
  - Włączanie i wyłączanie buzzera (zapis `1` lub `0` do pliku sysfs).
  - Odczytywanie stanu aktywnego bezpośrednio z sysfs.
  - Bezpieczny fallback w przypadku braku pliku w sysfs (np. w środowisku testowym bez fizycznej płytki).
- Wszystkie testy jednostkowe aplikacji przechodzą pomyślnie.
