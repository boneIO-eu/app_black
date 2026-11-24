# Kilka magistral Modbus — plan implementacji

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `modbus:` jako lista magistral (wbudowane RS485 `uart4` + przejściówki USB), urządzenia przypięte polem `bus:`, bez zmiany ID encji.

**Architecture:** Nowy moduł `boneio/core/config/modbus_buses.py` trzyma całą logikę „które urządzenie na której magistrali” i reguły zapisu. Używają go model, manager i trasa zapisu. `ModbusManager` trzyma `dict[bus_id, Modbus]`. Migracja v9 przepisuje stary słownik na listę w pamięci i w pliku.

**Tech Stack:** Python 3.13, pydantic v2 (modele sekcji), pymodbus, FastAPI, React + TS (vitest), pytest + pytest-asyncio.

**Spec:** `docs/superpowers/specs/2026-11-24-modbus-multi-bus-design.md`

## Global Constraints

- Gałąź `dev-1.7`, worktree `app_black-1.7`. Nie dotykać `dev-debian13`.
- Commity bez żadnej stopki AI (`Co-Authored-By`, „Generated with…”). Jeden commit na funkcję (pod changelog).
- Stage'ować tylko własne pliki, przez prywatny indeks: `idx=$(mktemp); cp "$(git rev-parse --git-path index)" $idx; GIT_INDEX_FILE=$idx git add <pliki>; GIT_INDEX_FILE=$idx git commit -m …; git reset -q -- <pliki>`.
- Nie uruchamiać `pre-commit run`.
- W docstringach niezmienniki, nie historia; żadnych ID audytu.
- ID urządzenia: `_get_device_id_from_config` bez zmian, magistrala **nie** wchodzi do ID.
- Zapis ścisły, start pobłażliwy: panel odrzuca, start pomija z błędem w logu i wstaje.
- `port`: klucz `UARTS` albo ścieżka pasująca do `^/dev/(serial/by-id/[^/.][^/]*|serial/by-path/[^/.][^/]*|ttyUSB\d+|ttyACM\d+)$`. Nic innego.
- Id magistrali: `^[a-z0-9_]+$`. Id po migracji ze starego configu: `rs485`.
- Bez nowych zależności (Python i npm).
- Po zmianie modeli: `python -m boneio.core.config.json_schema` i commit wygenerowanego schematu.
- Testy: `uv run pytest <ścieżka> -q` (frontend: `cd frontend && npx vitest run <plik>`).

## Review Focus

1. Przejściówka USB odłączona przy starcie → tylko ta magistrala nie działa, `uart4` i jego urządzenia działają normalnie (Task 3: `test_missing_usb_port_does_not_stop_other_bus`).
2. Config ze sterownika 0.2/0.3 (`modbus: {uart: uart1}`) → po migracji `port: uart1`, Modbus działa jak przed aktualizacją (Task 2: `test_uart1_config_keeps_its_port`).
3. Sekcja `modbus` z komentarzami albo w pliku z `!include` → migracja zachowuje komentarze i pisze do właściwego pliku (Task 2: `test_file_migration_keeps_comments`, `test_file_migration_follows_include`).
4. Dwa identyczne urządzenia bez `id` (adres 1, ten sam model) na dwóch magistralach → zapis odrzucony z prośbą o `id`, przy starcie drugie pominięte, pierwsze działa (Task 1: `test_duplicate_resolved_device_ids_refused`, Task 3: `test_duplicate_device_id_skipped_at_start`).
5. Zamiana kolejności magistral w panelu, gdy urządzenia nie mają `bus` → zapis odrzucony, zamiast po cichu przenieść urządzenia (Task 4: `test_reorder_that_moves_implicit_devices_refused`).

---

### Task 1: Model listy magistral i pole `bus`

**Files:**
- Create: `boneio/core/config/modbus_buses.py`
- Modify: `boneio/core/config/models/sensors.py:110-124` (model `Modbus` → `ModbusBus`), `:161-190` (`ModbusDevice.bus`), `:305-315` (sekcje `modbus` i `modbus_devices`)
- Modify: wygenerowany schemat JSON (komenda z Global Constraints)
- Test: `tests/unit/core/config/test_modbus_buses.py`

**Interfaces:**
- Produces (`boneio/core/config/modbus_buses.py`):
  - `PORT_PATTERN: str` (regex z Global Constraints)
  - `serial_device(port: str) -> str` — `UARTS[port][ID]` dla nazwy UART, w przeciwnym razie `port` bez zmian
  - `device_bus(device: dict, buses: list[dict]) -> str | None` — `device["bus"]` jeśli podane, inaczej `buses[0]["id"]`, `None` gdy brak magistral
  - `bus_reference_errors(devices: list[dict], buses: list[dict]) -> list[str]` — jedna linia na urządzenie wskazujące nieistniejące `id`
  - `bus_change_errors(old_buses: list[dict], new_buses: list[dict], devices: list[dict]) -> list[str]` — błąd, gdy jakiekolwiek urządzenie ma inne `device_bus(...)` dla nowej listy niż dla starej albo `None` dla nowej (obejmuje usunięcie, zmianę nazwy i zmianę kolejności przy urządzeniach bez `bus`). Komunikat wymienia ID urządzeń (`ModbusManager._get_device_id_from_config` → przenieść tę logikę jako `device_id(device: dict) -> str` do tego modułu i wołać ją z managera).
- Produces (model): sekcja `modbus` = `list[ModbusBus]`, `ModbusBus(id, port, baudrate, stopbits, bytesize, parity, timeout, inter_device_delay)` z dzisiejszymi domyślnymi; `ModbusDevice.bus: str | None = None`.

- [ ] **Step 1: Testy (wszystkie mają failować)**

```python
def test_bus_list_is_valid():
    assert models.validate("modbus", [{"id": "rs485", "port": "uart4"},
        {"id": "pompa", "port": "/dev/serial/by-id/usb-FTDI_FT232R-if00-port0", "parity": "E"}]) == []

@pytest.mark.parametrize("port", ["/dev/ttyS1", "/dev/serial/by-id/..", "/etc/passwd", "uart9", "/dev/sda"])
def test_port_outside_pattern_refused(port):
    assert models.validate("modbus", [{"id": "a", "port": port}])

def test_duplicate_bus_id_refused(): ...      # dwa razy id "a" → błąd
def test_duplicate_bus_port_refused(): ...    # dwa razy port "uart4" → błąd
def test_duplicate_resolved_device_ids_refused():
    errs = models.validate("modbus_devices", [{"address": 1, "model": "sdm630"},
        {"address": 1, "model": "sdm630", "bus": "pompa"}])
    assert any("id" in e for e in errs)

def test_serial_device():
    assert serial_device("uart4") == "/dev/ttyS4"
    assert serial_device("/dev/ttyUSB0") == "/dev/ttyUSB0"

def test_device_bus_defaults_to_first():
    assert device_bus({"address": 1}, [{"id": "a"}, {"id": "b"}]) == "a"
    assert device_bus({"bus": "b"}, [{"id": "a"}, {"id": "b"}]) == "b"
    assert device_bus({}, []) is None

def test_bus_reference_errors():
    assert bus_reference_errors([{"id": "x", "address": 1, "model": "m", "bus": "nope"}], [{"id": "a"}])

def test_reorder_moves_implicit_devices():
    devs = [{"address": 1, "model": "m"}]
    assert bus_change_errors([{"id": "a"}, {"id": "b"}], [{"id": "b"}, {"id": "a"}], devs)
    assert bus_change_errors([{"id": "a"}], [{"id": "a"}, {"id": "b"}], devs) == []
def test_rename_or_delete_used_bus_refused(): ...  # urządzenie z bus "b", nowa lista bez "b" → błąd
```

- [ ] **Step 2:** `uv run pytest tests/unit/core/config/test_modbus_buses.py -q` → FAIL (ImportError).
- [ ] **Step 3:** Zaimplementować moduł i modele. Unikalność `id`/`port` magistral i wyliczonych ID urządzeń jako `AfterValidator` na liście (wzór: `unique_resolved_ids` w `models/base.py:136`, ale klucz z `device_id`). `bus_reference_errors` **nie** jest w modelu sekcji (sekcja nie widzi drugiej sekcji); używają go Task 3 i Task 4.
- [ ] **Step 4:** Test → PASS. Dodatkowo `uv run pytest tests/unit/core/config tests/unit/core/test_modbus_schema.py -q` → PASS (zaktualizować fixtury, które mają `modbus:` jako słownik, na listę).
- [ ] **Step 5:** Przegenerować schemat JSON, commit `feat(modbus): sekcja modbus jako lista magistral`.

### Task 2: Migracja v9 i configi fabryczne

**Files:**
- Create: `boneio/core/config/migrations/v9_modbus_buses.py`
- Modify: `boneio/core/config/migrations/__init__.py` (`CURRENT_SCHEMA_VERSION = 9`, wpis `9: "1.7.0devN"` — N = najbliższy niewydany dev 1.7, sprawdzić `git tag`), import modułu tam, gdzie są importowane v1–v8
- Modify: `boneio/factory_config/*/*/config.yaml` (wszystkie: `modbus:\n  - id: rs485\n    port: uart4`)
- Modify: `boneio/webui/routes/update.py:999-1006` (regex podmienia `port: uart4` w nowym kształcie)
- Test: `tests/unit/core/test_v9_modbus_buses.py`

**Interfaces:**
- Consumes: kształt listy z Task 1.
- Produces: `migrate_v9_modbus_buses(doc: dict) -> dict`, `_persist(config_file: str) -> None`.

- [ ] **Step 1: Testy** (styl jak `tests/unit/core/test_v8_dead_entries.py`, `config_version: 8` w nagłówku)

```python
def test_dict_becomes_single_bus():
    out = migrate_v9_modbus_buses({"modbus": {"uart": "uart4", "baudrate": 19200, "parity": "E"}})
    assert out["modbus"] == [{"id": "rs485", "port": "uart4", "baudrate": 19200, "parity": "E"}]
def test_list_left_alone(): ...               # już lista → bez zmian
def test_no_modbus_section_left_alone(): ...
def test_uart1_config_keeps_its_port(): ...   # {"uart": "uart1"} → port "uart1"
def test_file_migration_keeps_comments(tmp_path): ...   # komentarz w bloku modbus przeżywa, wynik waliduje się validate_section("modbus", …) == []
def test_file_migration_follows_include(tmp_path): ...   # modbus: !include modbus.yaml → zmieniony modbus.yaml, config.yaml bez zmian w tej linii
def test_file_backup_written(tmp_path): ...  # backups/<plik>.pre-v9 istnieje
def test_factory_configs_validate():
    for f in glob.glob("boneio/factory_config/*/*/config.yaml"):
        assert validate_section("modbus", load_yaml_file(f)["modbus"], None) == []
```

- [ ] **Step 2:** → FAIL.
- [ ] **Step 3:** `migrate_dict`: słownik → `[{"id": "rs485", "port": <uart>, **reszta}]`. `_persist`: edycja linii jak `v8_dead_entries._persist` (węzeł `modbus` z `yaml.compose`, kopia do `backups/<plik>.pre-v9`, cofnięcie, gdy wynik nie czyta się jako zamierzona lista). Blok: pierwsza linia dziecka zastąpiona przez `  - id: rs485`, wszystkie linie bloku (łącznie z komentarzami) wcięte o 2 spacje, klucz `uart:` → `port:`.
- [ ] **Step 4:** → PASS; plus `uv run pytest tests/unit/core/test_migration_consistency.py tests/unit/core/test_config_version_guard.py -q`.
- [ ] **Step 5:** Commit `feat(modbus): migracja v9 — stara sekcja modbus na listę magistral`.

### Task 3: Manager z wieloma magistralami

**Files:**
- Modify: `boneio/modbus/client.py:173-260` (`Modbus.__init__(self, port: str, ...)`; usunąć sprawdzanie RX/TX i `ModbusUartException` z tej ścieżki; `PORT_KEY` w `FailureLog` → per instancja, z nazwą portu)
- Modify: `boneio/core/manager/modbus.py` (całość: `_modbus` → `_buses: dict[str, Modbus]`)
- Modify: `boneio/core/manager/manager.py:242-246` (bez zmian w wywołaniu, sprawdzić typ `modbus_config: list[dict]`)
- Modify: `boneio/webui/routes/dev_fake_device.py`, `tests/mocks/modbus.py` — dostosować do `get_modbus_client(bus=None)`
- Test: `tests/unit/modbus/test_multi_bus_manager.py`

**Interfaces:**
- Consumes: `serial_device`, `device_bus`, `device_id` z Task 1.
- Produces:
  - `Modbus(port: str, baudrate=9600, stopbits=1, bytesize=8, parity="N", timeout=1.5, inter_device_delay=5)` — `port` to ścieżka `/dev/...` (wołający robi `serial_device`)
  - `ModbusManager.get_modbus_client(bus: str | None = None) -> Modbus | None` — `None` → pierwsza magistrala
  - `ModbusManager.bus_ids() -> list[str]`
  - `_coordinator_inputs(...)` zawiera `"bus": <id>`, więc zmiana `bus` przy reload wymusza odbudowę koordynatora (istniejący mechanizm `_coordinator_built_from`)

- [ ] **Step 1: Testy** (z `BONEIO_DEV=1 BONEIO_MODBUS_SIM=1` przez `monkeypatch.setenv`, symulator per magistrala)

```python
def test_devices_land_on_their_bus(): ...       # 2 magistrale, urządzenie z bus "b" → coordinator.modbus is manager.get_modbus_client("b")
def test_device_without_bus_uses_first(): ...
def test_unknown_bus_device_skipped_at_start(caplog): ...   # reszta urządzeń działa, błąd w logu z nazwą magistrali
def test_duplicate_device_id_skipped_at_start(caplog): ...  # pierwsze zostaje, drugie pominięte z błędem
def test_missing_usb_port_does_not_stop_other_bus(): ...    # bez symulatora: port /dev/serial/by-id/nie-ma → manager wstaje, magistrala uart4 ma koordynatory
async def test_reload_moves_device_between_buses(): ...     # zmiana bus → koordynator odbudowany na nowej magistrali, ID bez zmian
def test_get_modbus_client_default_and_unknown(): ...       # None → pierwsza; "nope" → None
def test_devices_without_buses_warns(caplog): ...          # modbus: [] + urządzenia → start bez wyjątku, ostrzeżenie w logu
```

- [ ] **Step 2:** → FAIL.
- [ ] **Step 3:** Zaimplementować. Każda magistrala budowana w osobnym `try`, więc błąd jednej nie zatrzymuje pozostałych. `reload_modbus_devices` buduje nowe koordynatory przez `device_bus(...)` na aktualnej liście magistral (sama lista magistral nie przeładowuje się na gorąco — jak dziś).
- [ ] **Step 4:** → PASS; plus `uv run pytest tests/unit/modbus tests/unit/webui/test_mock_coordinator.py tests/unit/webui/test_mcp.py tests/unit/integration -q` (discovery, Loxone i MCP czytają koordynatory, nie magistrale).
- [ ] **Step 5:** Commit `feat(modbus): osobny klient na każdą magistralę`.

### Task 4: Reguły zapisu w panelu

**Files:**
- Modify: `boneio/webui/routes/config_core.py:812-844` (`_section_errors`)
- Test: `tests/unit/webui/test_modbus_bus_save.py`

**Interfaces:**
- Consumes: `bus_reference_errors`, `bus_change_errors` z Task 1; istniejące `_stored_section(section)`.
- Produces: zapis `modbus_devices` sprawdza `bus` wobec zapisanego `modbus`; zapis `modbus` sprawdza zmianę wobec zapisanego `modbus_devices`.

- [ ] **Step 1: Testy** (przez `_section_errors` z podmienionym `_stored_section`)

```python
async def test_device_with_unknown_bus_refused(): ...
async def test_delete_used_bus_refused(): ...          # komunikat zawiera ID urządzenia
async def test_rename_used_bus_refused(): ...
async def test_reorder_that_moves_implicit_devices_refused(): ...
async def test_add_second_bus_allowed(): ...
async def test_no_stored_modbus_skips_check(): ...     # brak zapisanej sekcji → bez dodatkowych błędów (jak przy unknown_targets)
```

- [ ] **Step 2:** → FAIL. **Step 3:** Dopisać dwa warunki w `_section_errors`. **Step 4:** → PASS. **Step 5:** Commit `feat(modbus): panel nie zgubi urządzeń przy zmianie magistral`.

### Task 5: Pomocnik Modbus i lista portów

**Files:**
- Create: `boneio/modbus/ports.py`
- Modify: `boneio/webui/routes/modbus.py` (modele żądań `:44-90`, trasy get/set/set_multiple/search/pause/configure-device, nowa `GET /modbus/ports`)
- Test: `tests/unit/webui/test_modbus_ports.py`, rozszerzyć `tests/unit/webui/test_modbus_tools_writes.py`

**Interfaces:**
- Consumes: `ModbusManager.get_modbus_client(bus)`, `bus_ids()` z Task 3.
- Produces:
  - `list_serial_ports(configured: Iterable[str], by_id_dir: str = "/dev/serial/by-id") -> list[dict]` — elementy `{"port": str, "label": str, "kind": "builtin" | "usb"}`; `builtin`: `uart4` plus nazwy UART z `configured`; `usb`: wpisy `by_id_dir` (`os.scandir`), etykieta z nazwy linku bez `usb-` i `-ifNN-portN`, brak katalogu → pusta lista USB
  - pole `bus: str | None = None` w `ModbusGetRequest`, `ModbusSetRequest`, `ModbusSetMultipleRequest`, `ModbusSearchRequest`, `ModbusPollingRequest`, `ModbusConfigureDeviceRequest` (w ostatnim `bus` zastępuje `uart`); nieznany `bus` → HTTP 404 `{"detail": "Unknown Modbus bus: <id>"}`
  - `GET /modbus/ports` → `{"ports": [...], "buses": [<id>, ...]}`

- [ ] **Step 1: Testy**

```python
def test_list_ports_reads_by_id(tmp_path):
    (tmp_path / "usb-FTDI_FT232R_USB_UART_A10K1234-if00-port0").symlink_to("/dev/null")
    ports = list_serial_ports(["uart4"], by_id_dir=str(tmp_path))
    assert {"port": "uart4", "label": "RS485 (uart4)", "kind": "builtin"} in ports
    assert any(p["kind"] == "usb" and "FTDI_FT232R" in p["label"] for p in ports)
def test_list_ports_without_by_id_dir(): ...   # nieistniejący katalog → tylko builtin
async def test_get_uses_requested_bus(): ...    # odczyt idzie do klienta "b"
async def test_unknown_bus_is_404(): ...
```

- [ ] **Step 2:** → FAIL. **Step 3:** Zaimplementować. **Step 4:** → PASS, plus `uv run pytest tests/unit/webui -q -k modbus`. **Step 5:** Commit `feat(modbus): pomocnik Modbus wybiera magistralę, lista portów USB`.

### Task 6: CLI

**Files:**
- Modify: `boneio/bonecli.py:76-82` (`--port`, z `--uart` jako aliasem; bez `choices`, walidacja wzorcem `PORT_PATTERN` lub kluczem `UARTS`), `:350-380`
- Modify: `boneio/modbus/cli.py` (parametr `port: str` zamiast `uart: str`; `Modbus(port=serial_device(port), ...)`)
- Test: `tests/unit/modbus/test_cli_port.py`

- [ ] **Step 1:** Testy: `--port /dev/ttyUSB0` i `--uart uart4` parsują się do tego samego pola; `--port /etc/passwd` → błąd parsera (`SystemExit`).
- [ ] **Step 2–4:** FAIL → implementacja → PASS. **Step 5:** Commit `feat(modbus): boneio modbus --port przyjmuje przejściówkę USB`.

### Task 7: Panel

**Files:**
- Modify: `frontend/src/components/UISettings/ModbusForm.tsx` (formularz jednej magistrali: `id`, `port` jako select z `GET /api/modbus/ports` + możliwość wpisania ścieżki, parametry linii)
- Modify: `frontend/src/components/UISettings/components/TableRenderer.tsx` (sekcja `modbus` jako lista, wzór `ModbusDeviceTable`) i ewentualnie `FormRenderer.tsx`
- Modify: `frontend/src/components/UISettings/ModbusDeviceForm.tsx` (select „Magistrala”, widoczny gdy magistral > 1; przy > 1 zapis zawsze z jawnym `bus`)
- Modify: `frontend/src/components/ModbusHelper.tsx:109,354,954-965` (select magistrali zamiast UART; `bus` we wszystkich wywołaniach `/api/modbus/*`)
- Modify: `frontend/src/locales/{pl,en}/common.json`
- Create: `frontend/src/components/UISettings/modbusBus.ts` + `modbusBus.test.ts`

**Interfaces:**
- Consumes: `GET /api/modbus/ports`, pole `bus` tras z Task 5, kształt sekcji z Task 1, błędy zapisu z Task 4 (wyświetlane jak inne błędy zapisu sekcji).
- Produces: `withExplicitBus(device: ModbusDeviceFormData, busIds: string[]): ModbusDeviceFormData` — przy `busIds.length > 1` i braku `bus` wpisuje `busIds[0]`; przy jednej magistrali zwraca bez zmian.

- [ ] **Step 1:** `modbusBus.test.ts`: `withExplicitBus({address: 1}, ["a"])` → bez `bus`; `withExplicitBus({address: 1}, ["a","b"])` → `bus: "a"`; z `bus: "b"` → bez zmian.
- [ ] **Step 2:** `cd frontend && npx vitest run src/components/UISettings/modbusBus.test.ts` → FAIL.
- [ ] **Step 3:** Zaimplementować helper i formularze.
- [ ] **Step 4:** vitest → PASS; `cd frontend && npx tsc -b && npm run lint` → bez błędów; `uv run pytest tests/unit/webui -q -k "settings and pages"` (headless test „każda strona ustawień się otwiera”) → PASS.
- [ ] **Step 5:** Commit `feat(panel): lista magistral Modbus i wybór magistrali urządzenia`.

### Task 8: Sprawdzenie na sprzęcie (.134)

- [ ] **Step 1:** Zbudować wheel lokalnie i wgrać na .134 według `reference-dev-controller` (`remote_test.sh`), z configiem w starym kształcie → po starcie `config.yaml` w nowym kształcie, `backups/*.pre-v9` istnieje, Modbus na `uart4` działa.
- [ ] **Step 2:** Wpiąć przejściówkę USB‑RS485, dodać w panelu magistralę z portem z listy i inną parzystością niż `uart4`, podpiąć urządzenie → obie magistrale odpytują równolegle, encje w HA mają te same ID co przed aktualizacją.
- [ ] **Step 3:** Wyjąć przejściówkę i zrestartować → `uart4` działa, w logu jeden komunikat o brakującym porcie.
