# Układ ustawień boneIO Black — plan przebudowy

Stan: punkty 1–6 wdrożone, zostaje 7 (obraz). Szczegóły na końcu dokumentu.
Powiązane: [SECURITY_ROADMAP_1.6.md](SECURITY_ROADMAP_1.6.md) (F-05 jest tu domykane inaczej, niż zakładała roadmapa).

## Problem

Dziś ustawienia są w dwóch miejscach: **Ustawienia** (sekcje z `config.yaml`, generowane ze schematu)
i **System** (stan systemu operacyjnego i usług). Do tego **Narzędzia** i **Edytor YAML** jako osobne
pozycje w górnym menu.

Podział przebiega wzdłuż **tego, gdzie dane leżą** — YAML kontra reszta systemu. To jest szczegół
implementacyjny, który wyciekł do interfejsu. Objawy:

- hasło, którym boneIO łączy się z brokerem, jest w Ustawieniach; hasła kont brokera są w Systemie,
- „Serwer Web" jest w Ustawieniach, a certyfikat, którym ten serwer jest podawany — w Systemie,
- nowa sekcja Bezpieczeństwo siłą rzeczy dotyczy obu, więc w żadnym z tych miejsc nie pasuje,
- „Narzędzia" istnieją dwa razy: jako pozycja w górnym menu i jako grupa w pasku bocznym Ustawień.

Użytkownik nie pyta „czy to siedzi w config.yaml". Pyta „jak zmienić hasło". Dostaje dwie odpowiedzi
w dwóch miejscach i musi znać naszą architekturę, żeby wybrać właściwą.

## Zasada

**Grupa nazywa pytanie, nie miejsce przechowywania danych.**

Konsekwencja, którą trzeba świadomie przyjąć: w jednej grupie staną obok siebie ustawienia z
`config.yaml` (wymagają zapisu i restartu albo przeładowania) i ustawienia systemowe (działają od
razu). Różnica jest prawdziwa, ale ma znaczenie **przy zapisie**, a nie przy szukaniu. Plakietka
„restart" per pozycja już istnieje i to ona niesie tę informację.

## Nowy układ

Jedno wejście: **Ustawienia**. Siedem grup.

### 1. Urządzenie — czym ten sterownik jest

| Pozycja | Skąd dziś |
|---|---|
| boneIO (nazwa, wersja płyty) | Ustawienia / restart |
| Obszary i pomieszczenia | Ustawienia |
| Nazwa hosta | System |
| Strefa czasowa | System |
| Wyświetlacz OLED | Ustawienia |
| Czujniki sterownika | Ustawienia / restart |
| Ekspandery: MCP23017, PCA9685, PCF8575 | Ustawienia (tylko MCP23017) — reszta bez UI |

### 2. Sterowanie — czym steruje

| Pozycja | Skąd dziś |
|---|---|
| Wyjścia lokalne, Grupy wyjść, Rolety | Ustawienia |
| Wejścia lokalne | Ustawienia |
| Sensory ADC, Czujki 1-Wire, Wirtualne sensory energii | Ustawienia |
| Szablony — w tym nawadnianie | Ustawienia |
| Macierz powiązań | Ustawienia / grupa „Narzędzia" |

Nawadnianie nie jest osobną pozycją: to platforma szablonu, konfigurowana przez `TemplateForm`
→ `IrrigationForm` wewnątrz sekcji Szablony. Obsługa na żywo zostaje w zakładce Szablony w górnym
menu.

### 3. Połączenia — dokąd boneIO się łączy

| Pozycja | Skąd dziś |
|---|---|
| Protokoły komunikacyjne — MQTT i Loxone UDP | Ustawienia / restart |
| Modbus (magistrala) + Urządzenia Modbus | Ustawienia |
| Magistrala CAN | Ustawienia / restart |
| Urządzenia zdalne + wejścia i wyjścia zdalne | Ustawienia / grupa „Zdalne" |
| Eksport dashboardu do Home Assistant | Narzędzia |

To jest sekcja o **wychodzeniu na zewnątrz**. U użytkownika, który przeniósł się na brokera w Home
Assistant, wpisane tu konto i hasło należą do HA, nie do nas.

### 4. Usługi na sterowniku — co działa na tym urządzeniu

| Pozycja | Skąd dziś |
|---|---|
| Broker MQTT (mosquitto) — status, konta, hasła, włącznik | System / „Hasła MQTT" |
| Node-RED — status, włącznik | System / NodeRedManagement |
| Caddy — proxy i certyfikat | System / SSL |

Wszystko to są usługi zainstalowane na sterowniku: można je włączyć, wyłączyć, mają własne
poświadczenia. **Node-RED zostaje osobną pozycją w górnym menu** — to osobna aplikacja w ramce, a nie
ustawienie; tutaj jest tylko jej włącznik i stan.

### 5. Dostęp — kto może wejść

| Pozycja | Skąd dziś |
|---|---|
| Przegląd bezpieczeństwa | Ustawienia / Bezpieczeństwo |
| Konta użytkowników | Ustawienia / „Panel webowy" |
| Panel webowy — port, proxy, osadzanie w ramce | Ustawienia / restart |
| Rejestracja w chmurze i certyfikat zaufany | Ustawienia (`web.cloud`) + System / SSL |

### 6. Konserwacja — utrzymanie w ruchu

| Pozycja | Skąd dziś |
|---|---|
| Aktualizacja oprogramowania | System |
| Kopie zapasowe | System |
| Migracje systemowe | System |
| Restart i wyłączenie | System |
| Autotest sprzętu | System |
| Błędy sprzętowe | System |
| Naprawa uprawnień aplikacji | System |
| Reset do ustawień fabrycznych | System |

### 7. Zaawansowane

| Pozycja | Skąd dziś |
|---|---|
| Edytor YAML | **górne menu** |
| Poziomy logowania (`logger`) | Ustawienia |

Edytor YAML schodzi z górnego menu do Ustawień jako skrót. Dla autora to narzędzie codzienne, dla
użytkownika końcowego pułapka, w której da się rozłożyć konfigurację jednym zapisem. Grupa
„Zaawansowane" jest właściwym ostrzeżeniem.

## Diagnostyka wchłania Narzędzia

„Narzędzia" to dziś cztery zakładki i **żadna z nich nic nie zapisuje**: skan I2C, skan Modbusa, skan
sieci CAN i eksport dashboardu HA. Klikasz i się dowiadujesz. To nie ustawienia.

Strona **Diagnostyka** (powstała w 1.6 z „Logi") dostaje więc:

- log urządzenia z wyszukiwaniem i agregacją powtórzeń,
- okno diagnostyczne (tymczasowy DEBUG, samo się zamyka),
- paczkę dla wsparcia,
- skany: I2C, Modbus, CAN.

Eksport dashboardu HA idzie do **Połączeń**, nie tutaj — to generator konfiguracji dla integracji,
a nie sprawdzanie sprzętu.

Zastrzeżenie do rozstrzygnięcia w praktyce: skan I2C bywa używany przy **dodawaniu** ekspandera, a nie
przy awarii. Jeśli okaże się, że ludzie szukają go przy konfiguracji sprzętu, warto zostawić skrót
w grupie Urządzenie.

## Górne menu

Przed (admin): Wyjścia, Wejścia, Czujniki, Modbus, Szablony | Narzędzia, Diagnostyka, **Ustawienia**,
**Edytor YAML**, **System**, Node-RED, Pomoc.

Po: Wyjścia, Wejścia, Czujniki, Modbus, Szablony | Diagnostyka, **Ustawienia**, Node-RED, Pomoc.

Siedem pozycji administracyjnych schodzi do czterech. `/system`, `/tools` i `/config` przekierowują,
tak jak zrobiliśmy z `/logs` → `/diagnostics`.

## Decyzja przekrojowa: mosquitto to nie jest MQTT

To dwie różne rzeczy i sklejenie ich byłoby aktywnie szkodliwe:

- **`mqtt:` w config.yaml** — dokąd boneIO się łączy. U użytkownika z brokerem w Home Assistant
  wpisane tam konto i hasło są *HA*.
- **mosquitto na sterowniku** — usługa z własnymi kontami, działająca lokalnie.

Gdyby „Hasła MQTT" stały w sekcji połączenia, użytkownik z brokerem w HA zobaczyłby je tuż pod
hasłem, które przed chwilą wpisał, i uznał, że to to samo. Zmieniłby hasło usługi, której nie używa.

Dlatego: **Połączenia** = dokąd wychodzimy, **Usługi na sterowniku** = co u nas działa.

### Kiedy broker lokalny wolno proponować do wyłączenia

Sterownik wychodzi od nas z **uruchomionym mosquitto i to jest celowe** — dzięki temu działa od razu,
a dodanie go do Home Assistant to dwa kliknięcia. Wyłączanie go z automatu byłoby psuciem produktu.

Reguła jest **stanowa**, tak jak przy wymuszaniu konta administratora:

- `mqtt.host` wskazuje localhost → broker jest w użyciu → hasło ma znaczenie, wyłączanie nie wchodzi
  w grę,
- `mqtt.host` wskazuje gdzie indziej → boneIO z niego nie korzysta → warto zaproponować wyłączenie.

W drugim przypadku komunikat musi mówić **„boneIO go nie używa"**, a nie „nikt go nie używa". Tego
drugiego nie wiemy — na brokerze może wisieć czyjeś ESP. Dałoby się to sprawdzić przez
`$SYS/broker/clients/connected` i wtedy komunikat mógłby być mocniejszy.

## F-05 rozwiązane inaczej, niż zakładała roadmapa

Roadmapa mówiła „rotacja domyślnego hasła MQTT". To jest naprawa złego problemu.

Dziś to samo hasło `boneio123` jest wypalane w **dwóch miejscach, które muszą się zgadzać**:

- `scripts/setup_boneio.sh:401-403` — trzy konta w `/etc/mosquitto/passwd`,
- `configs/*/mqtt.yaml` — po jednym na każdy wariant płyty.

### Plan: hasło generowane przy pierwszym starcie

Jednostka `oneshot` uruchamiana przed `boneio.service`, sterowana plikiem-znacznikiem:

1. znacznik istnieje → wyjdź,
2. wylosuj hasła,
3. wpisz je do `/etc/mosquitto/passwd`,
4. wpisz hasło konta `boneio` do `mqtt.yaml`,
5. zapisz hasło konta `homeassistant` do pliku `0600` czytelnego dla panelu,
6. przeładuj mosquitto, postaw znacznik.

Dwa miejsca dalej się zgadzają, a każde urządzenie jest inne. Spełnia to EN 303 645 §5.1-1 przez
**unikalne per urządzenie**, nie ruszając dwóch kliknięć w HA — i nie ma nic do nadrukowania ani do
śledzenia przy produkcji, bo hasło powstaje na urządzeniu.

### To poprawia onboarding, a nie psuje

Dziś dwa kliknięcia w HA wymagają, żeby użytkownik **znalazł `boneio123` w dokumentacji**. Z hasłem
per urządzenie panel może je po prostu pokazać: krok „Podłącz do Home Assistant" z adresem, portem,
kontem i hasłem gotowymi do skopiowania.

### Osobne hasło dla konta `homeassistant`

`homeassistant` to jedyne konto, które **opuszcza urządzenie**. Jego kompromitacja nie powinna od razu
dawać tożsamości boneIO na brokerze, więc dostaje własne hasło, trzymane w osobnym pliku `0600`.
Koszt: jeden plik więcej.

### Konto `mqtt` do usunięcia

Trzecie konto, `mqtt`, **nie jest używane nigdzie** — ani w `configs/`, ani w aplikacji, ani w
kontenerach. Ma tylko regułę w sudoers i wypalone domyślne hasło, czyli jest czystą powierzchnią
ataku. Do usunięcia razem z jego regułą `NOPASSWD`. `scripts/audit_image.sh` niech sprawdza, czy
zniknęło.

### Urządzenia już w terenie

Tam hasła **nie wolno zmienić po cichu** — to zerwie połączenie z Home Assistant. Przegląd
bezpieczeństwa *proponuje* rotację, ostrzega wprost, że trzeba zaktualizować HA, i **pokazuje nową
wartość**. Wymuszać nie można.

## Luki wykryte przy okazji

Dwa ekspandery, `pca9685` i `pcf8575`, nie mają formularza — w przeciwieństwie do `mcp23017`.
Konfiguruje się je wyłącznie edytorem YAML. W typach frontendu figurują, w interfejsie nie.

Nie planuję dorabiać im formularzy w tym kroku, ale w nowym układzie mają swoje miejsce
(Urządzenie → Ekspandery), więc luka staje się widoczna zamiast niewidocznej.

Uwaga metodologiczna. Pierwsza wersja tej listy była dłuższa o `irrigation` i `lox_udp` i **była
błędna**. Powstała z porównania kluczy najwyższego poziomu schematu z `sectionDefinitions.ts`, co
pomija wszystko osiągalne *przez* inną sekcję: nawadnianie przez Szablony, Loxone przez Protokoły
komunikacyjne. Nieobecność nazwy na liście sekcji nie oznacza braku UI.

## Kolejność wdrożenia

1. **Sekcje Systemu do paska bocznego Ustawień.** Są już rozbite na osobne komponenty w
   `SystemStateComponents/`, a pasek boczny już renderuje pozycje nie-schematowe (konta,
   bezpieczeństwo, macierz powiązań). To głównie przepinanie.
2. **Nowe grupy i przypisanie pozycji** — `sectionDefinitions.ts` plus nagłówki grup w
   `SettingsSidebar.tsx`.
3. **Rozdzielenie MQTT od mosquitto** — dwie osobne pozycje, w dwóch różnych grupach, z tekstem, który
   mówi, która jest która.
4. **Narzędzia do Diagnostyki**, eksport dashboardu do Połączeń.
5. **Edytor YAML do Zaawansowanych**, `/config` przekierowuje.
6. **Górne menu** — usunięcie trzech pozycji.
7. **Hasło per urządzenie** (obraz, `black_debian_images`) — osobno od przebudowy UI, bo to inna
   gałąź i inny cykl wydawniczy.

Punkty 1–6 są w `app_black` i można je wypuścić niezależnie od 7.

## Ryzyka

- **Zakładki, które ludzie mają w przeglądarce.** `/system`, `/tools`, `/config` muszą przekierowywać,
  a nie zwracać 404.
- **Pamięć mięśniowa.** Twoi obecni użytkownicy wiedzą, że aktualizacja jest w „System". Warto przez
  jedno wydanie zostawić w Konserwacji nagłówek z dawną nazwą.
- **Pasek boczny robi się długi.** Siedem grup razy kilka pozycji to około trzydziestu wpisów. Grupy
  powinny się zwijać, a otwarta pozostaje ta, w której się jest.
- **Tłumaczenia.** Siedem nazw grup plus opisy; reszta nazw pozycji bez zmian.


## Status wdrożenia

### Zrobione

- **Sekcje Systemu w pasku bocznym.** Strona `/system` już nie istnieje, `/system` przekierowuje
  na `/settings/update`. Górne menu schudło z siedmiu pozycji administracyjnych do czterech.
  Aktualizacja, narzędzia urządzenia i błędy sprzętowe są wybierane parametrem `SystemState`, nie
  rozbite na osobne pliki — flow aktualizacji instaluje firmware i nie da się go stąd przećwiczyć.
  Do rozbicia, gdy będzie zapasowy sterownik do przejścia pełnej aktualizacji.
- **Siedem grup.** Pozycje nie-schematowe idą przez rejestr `constants/standaloneSections.ts`
  zamiast łańcucha warunków w renderze.
- **Rozdzielenie mosquitto od MQTT.** Protokoły komunikacyjne są w Połączeniach, broker lokalny
  w Usługach na sterowniku. Check bezpieczeństwa wskazuje teraz na `mosquitto`, nie na kotwicę
  nieistniejącej już strony.
- **Zwijanie paska.** Zmierzone: telefon 2569 px → 704 px treści (3,73 → 1,35 ekranu), desktop
  ten sam spis → 922 px w kolumnie 602 px. Desktop dostał akordeon z otwartą grupą aktywnej
  sekcji, telefon dwa kroki — kafelki grup, potem sekcje. Filtr działa na obu i ignoruje grupy.

- **Narzędzia rozwiązane.** Skany I2C, Modbus i CAN są na stronie Diagnostyka, eksport dashboardu
  HA jest sekcją w Połączeniach. `/tools` przekierowuje.
- **Edytor YAML w Zaawansowanych**, `/config` przekierowuje. Górne menu ma cztery pozycje
  administracyjne: Diagnostyka, Ustawienia, Node-RED, Pomoc.
- **MCP23017 przeniesione do Zaawansowanych** — poprawne do skonfigurowania, łatwe do zepsucia
  i nieistotne dla kogoś, kto nie dołożył ekspandera.
- **Ostatnia zakładka zapamiętywana.** Wejście na `/settings` wraca tam, gdzie ostatnio byłeś,
  zamiast zawsze do Obszarów. Per przeglądarka, jak pozycja przewinięcia.

### Zostaje

- **Hasło per urządzenie** w obrazie — osobna gałąź, osobny cykl wydawniczy.
- **Certyfikat i proxy** (`SslSection`) — wyjęty z drzewa, bo jest oznaczony `hidden` od lutowego
  refaktoru i nigdy się nie renderował. Decyzja produktowa: odsłonić czy zostawić schowany.
- **Liczniki przy pozycjach** („Wyjścia 32", „Rolety 2") — rozważane, nieuzgodnione.
