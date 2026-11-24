# Kilka magistral Modbus na jednym boneIO Black

Gałąź: `dev-1.7`. Data: 2026-11-24.

## Po co

Wracają dwa zgłoszenia, które sprowadzają się do tego samego:

1. Część urządzeń Modbus RTU wymaga parzystości (E/O), część jej nie obsługuje
   (N). Na jednej linii z jednymi ustawieniami portu nie da się ich połączyć.
2. Pompa ciepła ze sterownikiem RX910‑SE21 ma Modbus tylko po RS232.
   Wbudowane RS485 tego nie obsłuży, potrzebny jest osobny port.

Oba przypadki rozwiązuje druga magistrala na przejściówce USB (USB‑RS485 albo
USB‑RS232) z własnymi ustawieniami portu.

## Sprzęt (ustalone)

- Wbudowana jest zawsze jedna magistrala RS485 na `uart4` (`/dev/ttyS4`).
- `uart1` to CAN (tylko sterowniki 0.2/0.3 miały na nim Modbus).
- Każda dodatkowa magistrala to przejściówka USB. Jądro 6.18 na obrazie ma
  `ftdi_sio`, `ch341`, `pl2303`, `cp210x` i `cdc_acm`. Użytkownik `boneio` jest
  w `dialout`, a usługa nie ogranicza urządzeń. Po stronie systemu nic nie
  trzeba dodawać (sprawdzone na .134).

## Cele

- `modbus:` to lista magistral, każda z własnym `id`, portem i parametrami
  linii.
- Urządzenie w `modbus_devices` wskazuje magistralę polem `bus:`. Bez `bus`
  trafia na pierwszą magistralę z listy.
- Port to `uart4` (lub inna nazwa z `UARTS` dla starych sterowników) albo
  ścieżka przejściówki USB, preferowana `/dev/serial/by-id/...`.
- Panel: lista magistral w ustawieniach Modbus z wyborem portu spośród
  wbudowanego RS485 i przejściówek, które system widzi. Pole „Magistrala” przy
  urządzeniu.
- Pomocnik Modbus (odczyt, zapis, skanowanie, pauza, konfiguracja urządzenia)
  i CLI `boneio modbus` działają na wybranej magistrali.
- Stare configi działają bez ręcznej edycji (migracja v9).

## Poza zakresem

- Różne ustawienia portu per urządzenie na jednym przewodzie (przełączanie
  parzystości przed odpytaniem). Odrzucone: część urządzeń przy błędzie
  ramki lub parzystości blokuje odbiór albo odpowiada śmieciami. Różna
  parzystość oznacza osobną magistralę.
- Modbus TCP.
- Definicja urządzenia dla pompy z RX910‑SE21 (osobne zadanie). Z flow
  Node-RED klienta: FC03, adres = liczba z PDF wprost (bez przesunięcia),
  unit 1, 9600 8N1, temperatury ×0,1. Kodowanie ujemnych do sprawdzenia.
- Drugi wbudowany UART (nie ma go na sterowniku).
- Wykrywanie podłączenia lub odłączenia przejściówki w locie. Magistrala bez
  portu zachowuje się jak dziś przy braku odpowiedzi, czyli encje stają się
  niedostępne. Po włożeniu przejściówki wystarcza przeładowanie Modbus lub
  restart.

## Czego nie wolno zepsuć

- ID urządzeń i encji w HA, tematy MQTT, klucze Loxone. Koordynatory dalej są
  kluczowane globalnie po ID urządzenia (`ModbusManager.get_all_coordinators`),
  niezależnie od magistrali. ID urządzenia musi więc pozostać unikalne w całym
  configu, nie w obrębie magistrali.
- Instalacje z jedną magistralą: po aktualizacji wszystko działa jak przed nią,
  a config po migracji czyta się naturalnie.

## Rozważone podejścia

- **A. Lista magistral z `id` (wybrane przez Pawła).** Ten sam wzorzec co
  inne sekcje-listy (`modbus_devices`, `mcp23017`), więc łatwo go pokazać
  w schemacie JSON i w panelu. Pierwszy element jest naturalną magistralą
  domyślną.
- B. Słownik `modbus:` jako główna magistrala plus `modbus_extra_buses:`.
  Bez migracji, ale dwa kształty na zawsze i wyjątkowa „pierwsza” w kodzie.
  Odrzucone.
- C. Słownik kluczowany nazwą magistrali. Ładniej w YAML, gorzej w schemacie
  i formularzu, brak naturalnej magistrali domyślnej. Odrzucone.

## Kształt configu

```yaml
modbus:
  - id: rs485
    port: uart4
    baudrate: 9600
    parity: N
  - id: pompa
    port: /dev/serial/by-id/usb-FTDI_FT232R_USB_UART_A10K1234-if00-port0
    baudrate: 9600
    parity: E
    timeout: 1500ms

modbus_devices:
  - id: licznik
    address: 1
    model: sdm630          # bez bus → pierwsza magistrala (rs485)
  - id: pc
    address: 1
    model: <definicja pompy>   # definicja RX910 to osobne zadanie
    bus: pompa
```

### Model `ModbusBus` (zastępuje dzisiejszy `Modbus`)

| pole | typ | uwagi |
|---|---|---|
| `id` | `^[a-z0-9_]+$` | wymagane, unikalne w liście |
| `port` | str | nazwa z `UARTS` albo ścieżka `/dev/...` (szczegóły niżej) |
| `baudrate`, `stopbits`, `bytesize`, `parity`, `timeout`, `inter_device_delay` | bez zmian | te same domyślne co dziś |

- `port`: dozwolone są klucze `UARTS` (`uart1`, `uart4`, …) i ścieżki pasujące
  do `^/dev/(serial/by-id/[^/]+|serial/by-path/[^/]+|ttyUSB\d+|ttyACM\d+)$`.
  Nic innego z `/dev` (to granica zaufania: config można wypchnąć z panelu).
- Walidacja listy: unikalne `id`, unikalny `port` (dwie magistrale na jednym
  porcie to błąd konfiguracji).
- `ModbusDevice.bus: str | None`. Zasada jak przy 1-Wire: **zapis ścisły,
  start pobłażliwy**. Panel nie zapisze urządzenia z `bus` wskazującym
  nieistniejącą magistralę. Przy starcie takie urządzenie jest pomijane
  z błędem w logu, a reszta wstaje.
- `modbus_devices` bez sekcji `modbus` (albo `modbus: []`): jak dziś, Modbus
  jest pomijany bez błędu walidacji. Do logu trafia ostrzeżenie, że
  urządzenia nie mają magistrali. *(Moja decyzja: dziś nie ma tu błędu, a
  nowy zablokowałby wczytanie starych configów.)*
- Pusta lista `modbus: []` oznacza Modbus wyłączony.

### Unikalność ID urządzeń *(moja decyzja)*

Urządzenie bez `id` dostaje ID `{address}_{model}`
(`ModbusManager._get_device_id_from_config`). Dwa takie same liczniki pod
adresem 1 na dwóch magistralach to typowy układ i dziś jeden z koordynatorów
po cichu nadpisałby drugi. Rozwiązanie:

- Walidator sekcji `modbus_devices` sprawdza unikalność **wyliczonych** ID
  (tak jak `unique_resolved_ids` w innych sekcjach). Przy kolizji komunikat
  każe nadać jawne `id`.
- Schemat generowania ID się nie zmienia (magistrala nie wchodzi do ID), więc
  HA, MQTT i Loxone nie widzą żadnej różnicy.
- Start pobłażliwy: przy kolizji w configu z dysku drugie urządzenie jest
  pomijane z błędem w logu (dziś jest nadpisywane po cichu).

### Magistrala domyślna, zmiana nazwy i usuwanie *(moja decyzja)*

- „Bez `bus` → pierwsza magistrala” zostaje wyłącznie dla zgodności
  z configami z jedną magistralą.
- Gdy magistral jest więcej niż jedna, panel przy zapisie urządzenia zawsze
  wpisuje jawne `bus:`. Zmiana kolejności magistral nie przenosi wtedy
  urządzeń zapisanych z panelu.
- Zapis sekcji `modbus` sprawdza `modbus_devices` z dysku i odrzuca:
  usunięcie magistrali, której używa jakieś urządzenie (jawnie albo jako
  domyślnej pierwszej), zmianę jej `id` oraz zmianę kolejności, która
  przeniosłaby urządzenia bez `bus` na inną magistralę. Komunikat podaje
  urządzenia. Automatyczne przepisywanie `bus` w urządzeniach odpada, bo
  zapis jednej sekcji nie powinien edytować innej.

### Migracja v9 (`boneio/core/config/migrations/v9_modbus_buses.py`)

- `migrate_dict`: gdy `modbus` jest słownikiem, zamienia go na
  `[{id: "rs485", port: <uart>, ...reszta pól}]`. Klucz `uart` przemianowuje
  na `port`. `modbus_devices` zostaje nietknięte (bez `bus` → pierwsza).
- `migrate_file`: to samo w pliku, edycją linii jak v7/v8 (komentarze,
  `!secret` i `!include` przeżywają; kopia `backups/<plik>.pre-v9`, cofnięcie
  edycji, która nie czyta się zgodnie z zamiarem). Sekcja może być w pliku
  dołączonym przez `!include`.
- `CURRENT_SCHEMA_VERSION = 9`, wpis w `SCHEMA_VERSION_APP_MAP` (wersja 1.7
  devN, w której wejdzie).
- Przywracany stary backup przechodzi tę samą ścieżkę migracji co wczytanie.

## Runtime

- `ModbusManager` trzyma `dict[bus_id, Modbus]` zamiast jednego `_modbus`.
  Każdy `Modbus` ma swój klient pymodbus, blokadę, pulę wątków i
  `FailureLog`. Magistrale nie blokują się nawzajem.
- `Modbus.__init__` przyjmuje ścieżkę portu (str) zamiast słownika UART.
  Sprawdzanie pinów RX/TX znika: nazwa z `UARTS` zamienia się na
  `/dev/ttySx` przy budowie, ścieżka USB idzie wprost. Klucz
  `PORT_KEY` w `FailureLog` (dziś stały) staje się per magistrala, żeby logi
  mówiły, który port nie odpowiada.
- Koordynator dostaje `Modbus` swojej magistrali. `reload_modbus_devices`
  uwzględnia zmianę `bus` urządzenia (przeniesienie = usunięcie i utworzenie
  koordynatora na nowej magistrali, bez zmiany ID).
- Zmiana parametrów magistrali (sekcja `modbus`) działa jak dziś: wymaga tego,
  czego wymaga dziś (restart lub przeładowanie, bez nowej ścieżki na gorąco).
- Brak urządzenia `/dev/serial/by-id/...` przy starcie: magistrala powstaje,
  połączenie się nie udaje, encje niedostępne, w logu jeden komunikat
  z nazwą portu (bez spamu, jak dziś `FailureLog`). Reszta magistral działa.
- Symulator (`simulator_enabled()`) działa per magistrala jak dziś.

## API i panel

- `ModbusManager.get_modbus_client(bus: str | None = None)` zwraca klienta
  magistrali, a domyślnie pierwszej. Trasy pomocnika (`/modbus/get`, `/set`,
  `/set_multiple`, `/search/stream`, `/pause`, `/configure-device`) dostają
  opcjonalne pole `bus`. Odpowiedź przy nieznanym `bus`: 4xx z czytelnym błędem.
- Nowa trasa `GET /modbus/ports`: wbudowane porty (dziś `uart4`; `uart1` tylko
  gdy sterownik jest 0.2/0.3 albo config go już używa) oraz wpisy
  z `/dev/serial/by-id/` z czytelną nazwą (producent/model z nazwy linku).
  Bez nowych zależności (`os.scandir` + `os.path.realpath`).
- `ModbusForm.tsx`: edycja listy magistral (dodaj/usuń, id, port z listy
  z `/modbus/ports` z możliwością wpisania ścieżki ręcznie, parametry linii).
- Formularz urządzenia Modbus: pole „Magistrala” (select z `id`), widoczne,
  gdy magistral jest więcej niż jedna.
- `ModbusHelper.tsx`: wybór magistrali zamiast martwego wyboru UART
  (dziś `configUart` trafia do trasy tylko jako tekst w logu).
- Schemat JSON przegenerowany z modeli (`python -m boneio.core.config.json_schema`).
- Tłumaczenia pl/en dla nowych etykiet.

## Pozostałe miejsca, które czytają `modbus` jako słownik

- `boneio/webui/routes/update.py:999` – podmiana `uart: uart4` regexem
  w configu fabrycznym dla 0.2/0.3 → nowy kształt (`port:`).
- `boneio/factory_config/*/*/config.yaml` – nowy kształt listy.
- `boneio/bonecli.py` + `boneio/modbus/cli.py` – `--uart` z `choices` →
  `--port` przyjmujący nazwę UART lub ścieżkę (`--uart` jako alias).
- `boneio/webui/routes/mcp.py`, `discovery.py`, `lox_template.py`,
  `dashboard.py` – sprawdzić, czy zakładają jeden `_modbus` (discovery czyta
  `_modbus_coordinators`, co się nie zmienia).
- Restore backupu: dopasowanie sprzętu (`hardware_fit.py`) istnieje tylko
  niezacommitowane w 1.6 (`../app_black`), na `dev-1.7` go nie ma. **Poza
  zakresem.** Przy przenoszeniu do 1.7 musi obsłużyć listę: zmienia `port`
  wbudowanej magistrali (`uart*`), a ścieżek USB nie rusza.

## Testy

- Model: stary słownik → lista po migracji; `bus` wskazujący nieistniejącą
  magistralę → błąd przy zapisie i pominięcie przy starcie; zduplikowane
  `id`/`port` → błąd; ścieżka spoza wzorca → błąd; dwa urządzenia bez `id`
  o tym samym adresie i modelu na różnych magistralach → błąd z prośbą
  o jawne `id`.
- Zapis sekcji `modbus`: usunięcie lub zmiana nazwy używanej magistrali →
  odrzucone.
- Migracja v9 na pliku: z komentarzami, z `!include`, z `uart1` (0.2/0.3).
- Manager: dwie magistrale (symulator), urządzenia trafiają na właściwego
  klienta; przeniesienie urządzenia między magistralami przy reload.
- Trasy pomocnika z `bus` i bez.
- Na sprzęcie (.134): przejściówka USB‑RS485 jako druga magistrala z inną
  parzystością niż `uart4`, oba urządzenia odpytywane równolegle.

## Zostawione budowniczemu

- Podział na commity (osobne pod changelog: model+migracja, runtime, trasy,
  panel, CLI).
- Dokładny wygląd listy magistral w panelu, w stylu istniejących list ustawień.
