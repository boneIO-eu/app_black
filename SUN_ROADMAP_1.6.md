# Funkcje słoneczne boneIO Black → 1.6.x

Cel: akcje i warunki odniesione do lokalnego położenia Słońca — wschód, zachód, zmierzchy
(cywilny, żeglarski, astronomiczny), złota i niebieska godzina, wysokość nad horyzontem.

Dokument projektowy. Kod jeszcze nie istnieje — to plan wdrożenia rozbity na fazy,
z których każda jest samodzielnie wypuszczalna w 1.6.x (ta sama zasada co
`SECURITY_ROADMAP_1.6.md`).

---

## 1. Co dziś jest, a czego brakuje

| Element | Stan |
|---|---|
| Warunki akcji (`time`, `date`, `state`) | Jest — `boneio/core/utils/conditions.py` + szybka ścieżka `boneio/core/manager/action_conditions.py` |
| Prekompilacja warunków przy ładowaniu configu | Jest — `manager.py:687` (`precompile_conditions`) |
| Ocena warunków na hot-path | Jest — `manager.py:940` (`should_execute_action`), jedno `datetime.now()` na batch |
| Strefa czasowa systemu + NTP | Jest — `webui/routes/system.py:860`, `timezone_sudoers.py`, UI `TimezoneSection.tsx` |
| Harmonogram punktowy w czasie | Jest jako prymityw — `core/events/bus.py:372` `async_track_point_in_time` |
| Harmonogram z configu | Tylko w nawadnianiu — `components/irrigation/controller.py:1143` |
| **Współrzędne urządzenia** | **Brak** — nigdzie w configu nie ma `latitude`/`longitude` |
| **Obliczenia pozycji Słońca** | **Brak** — brak `astral` i brak własnej implementacji |
| **Wyzwalacz czasowy akcji** | **Brak** — akcje odpalają wyłącznie wejścia GPIO / zdarzenia |

Wniosek: żeby „zamknij rolety o zachodzie" zadziałało, potrzebne są **trzy** cegły, nie jedna:
lokalizacja, silnik słoneczny i wyzwalacz. Sam warunek `type: sun` daje tylko bramkowanie
istniejących akcji („włącz światło w przedpokoju, ale dopiero po zmierzchu") — co też jest
wartościowe i jest wyraźnie tańsze.

---

## 2. Silnik słoneczny

### 2.1 Własna implementacja zamiast `astral`

Rekomendacja: **własny moduł `boneio/core/utils/sun.py`** (~250 linii), bez nowej zależności runtime.

Za:
- `pyproject.toml` pinuje wszystkie wersje co do znaku; każda nowa paczka to nowy element
  łańcucha dostaw na urządzeniu, które wisi w sieci klienta. Dla ~250 linii trygonometrii
  to zły interes.
- Progi `-6/-12/-18/-4/+6` to jedna funkcja z parametrem. Nie potrzebujemy 90% API `astral`.
- Pełna kontrola nad zachowaniem w strefach polarnych i nad polityką cache'u.

Przeciw (i jak to spinamy): ryzyko błędu w algorytmie. Domykamy testem — `astral`
ląduje w `[tool.pdm.dev-dependencies] test` i test porównuje nasze wyniki z jego
dla siatki (szerokość × data) z tolerancją 60 s. Zależność deweloperska, nie trafia na sprzęt.

### 2.2 Algorytm

NOAA Solar Calculator (uproszczony Meeus). Dokładność ~±1 min dla |φ| < 72°, co jest
o rząd wielkości lepsze niż potrzeba do sterowania roletami.

```
n        = dni juliańskie od J2000
L        = 280.460 + 0.9856474·n                     (średnia długość ekliptyczna)
g        = 357.528 + 0.9856003·n                     (anomalia średnia)
λ        = L + 1.915·sin g + 0.020·sin 2g            (długość ekliptyczna)
ε        = 23.439 - 0.0000004·n                      (nachylenie ekliptyki)
δ        = asin(sin ε · sin λ)                       (deklinacja)
EoT      = równanie czasu [min]
noon_utc = 720 - 4·lon - EoT                         [min UTC]
cos H    = (sin h₀ - sin φ·sin δ) / (cos φ·cos δ)
t(h₀)    = noon_utc ∓ 4·H                            [min UTC]
```

- `h₀` — próg wysokości dla danego zdarzenia (tabela niżej).
- Jedna iteracja poprawkowa: δ i EoT liczone ponownie dla wstępnie oszacowanej godziny
  zdarzenia, nie dla południa. Bez tego błąd rośnie do ~2 min w okolicy równonocy.
- Wysokość n.p.m. obniża horyzont: `h₀ -= 0.0353·√(elevation_m)` (110 m → −0.37°,
  czyli ~2 min różnicy w Polsce — mierzalne, więc warte uwzględnienia).
- Refrakcja i średnica tarczy są już wliczone w `-0.833°` dla wschodu/zachodu.

### 2.3 Zdarzenia i progi

| Kotwica (`anchor`) | Próg h₀ | Kierunek | Uwagi |
|---|---|---|---|
| `astronomical_dawn` / `astronomical_dusk` | −18° | ↑ / ↓ | koniec/początek nocy żeglarskiej |
| `nautical_dawn` / `nautical_dusk` | −12° | ↑ / ↓ | horyzont morski widoczny |
| `blue_hour_morning_start` / `blue_hour_evening_end` | −6° | ↑ / ↓ | = zmierzch cywilny |
| `civil_dawn` / `civil_dusk` | −6° | ↑ / ↓ | alias powyższych, czytelniejszy |
| `blue_hour_morning_end` / `blue_hour_evening_start` | −4° | ↑ / ↓ | |
| `golden_hour_morning_start` / `golden_hour_evening_end` | −4° | ↑ / ↓ | złota godzina styka się z niebieską |
| `sunrise` / `sunset` | −0.833° | ↑ / ↓ | środek tarczy + refrakcja |
| `golden_hour_morning_end` / `golden_hour_evening_start` | +6° | ↑ / ↓ | |
| `solar_noon` / `solar_midnight` | — | — | ekstremum, zawsze istnieje |

Fazy (test przynależności, **nie** podział rozłączny — złota i niebieska godzina
zachodzą na dzień i zmierzch cywilny):

| Faza | Warunek na wysokość |
|---|---|
| `day` / `above_horizon` | h > −0.833° |
| `civil_twilight` | −6° < h ≤ −0.833° |
| `nautical_twilight` | −12° < h ≤ −6° |
| `astronomical_twilight` | −18° < h ≤ −12° |
| `night` | h ≤ −18° |
| `golden_hour` | −4° ≤ h ≤ +6° |
| `blue_hour` | −6° ≤ h < −4° |

### 2.4 API modułu

```python
# boneio/core/utils/sun.py
def solar_position(lat: float, lon: float, when: datetime) -> tuple[float, float]:
    """Zwraca (elevation°, azimuth°) dla momentu `when` (aware UTC)."""

def event_time(lat: float, lon: float, day: date, h0: float, *, rising: bool,
               elevation_m: float = 0.0) -> datetime | None:
    """Moment przecięcia progu h0 danego dnia (aware UTC) albo None,
    gdy Słońce tego dnia progu nie przekracza (dzień/noc polarna)."""

def all_anchors(lat: float, lon: float, day: date,
                elevation_m: float = 0.0) -> dict[str, datetime | None]:
    """Wszystkie 18 kotwic dla jednego dnia lokalnego. Liczone raz na dobę."""

def phase_of(elevation: float) -> str:
    """Nazwa fazy podstawowej (day/civil_twilight/.../night)."""
```

Koszt: ~30 operacji trygonometrycznych na kotwicę. 18 kotwic raz na dobę na BBB
(Cortex-A8 1 GHz) to ułamek milisekundy. `solar_position` na żądanie ~10 µs —
bez problemu można wołać na hot-path, ale i tak cache'ujemy.

---

## 3. Lokalizacja w konfiguracji

Nowa sekcja najwyższego poziomu w `boneio/schema/schema.yaml`
(nie w `boneio:` — tamta sekcja opisuje sprzęt, nie miejsce jego instalacji):

```yaml
location:
  latitude: 52.2297      # -90..90,  wymagane
  longitude: 21.0122     # -180..180, wymagane
  elevation: 110         # m n.p.m., opcjonalne, domyślnie 0
```

Strefa czasowa **nie** trafia tutaj — bierzemy ją z systemu (`timedatectl`), tak jak
robi to już `TimezoneSection`. Dwa źródła prawdy dla strefy to gwarantowany dryf.

Walidacja przy ładowaniu:
- zakresy jak wyżej,
- `0.0, 0.0` → ostrzeżenie „prawdopodobnie niewypełnione" (Null Island),
- precyzja obcinana do 4 miejsc po przecinku (~11 m). Dokładniejsza nie daje nic
  dla obliczeń, a współrzędne wyciekają w kopii zapasowej configu i w `GET /api/config`.
  Warto to zapisać w dokumentacji użytkownika obok maskowania haseł (pkt 4 roadmapy bezpieczeństwa).

### Skąd użytkownik ma wziąć współrzędne

1. **Wpis ręczny** — zawsze działa, zawsze dostępny.
2. **Geolokalizacja przeglądarki** — `navigator.geolocation` wymaga bezpiecznego kontekstu.
   Panel boneIO w LAN po HTTP go nie ma, więc przycisk działa tylko przy dostępie po HTTPS
   albo z `localhost`. Ukrywamy go, gdy `!window.isSecureContext`, zamiast pokazywać
   przycisk, który po cichu nic nie robi.
3. **Wstępne wypełnienie ze strefy czasowej** — mała tablica `tz → (lat, lon)` (~450 wpisów,
   kilkanaście kB) po stronie frontendu. `Europe/Warsaw` → `52.23, 21.01`. Nie jest dokładne,
   ale dla wschodu/zachodu w obrębie jednej strefy błąd to minuty, a użytkownik dostaje
   działającą wartość domyślną bez internetu i bez mapy.

Mapy świadomie nie ma: kafle to zewnętrzny host, czyli CSP, internet na urządzeniu i kolejne
MB w bundlu — wszystko trzy rzeczy, których to urządzenie nie potrzebuje.

---

## 4. Warunek `type: sun`

### 4.1 Składnia

Trzy wzajemnie wykluczające się tryby w jednym typie warunku:

```yaml
# a) okno między kotwicami (najczęstszy przypadek)
condition:
  type: sun
  after: sunrise
  after_offset: "-30min"
  before: civil_dusk

# b) faza
condition:
  type: sun
  phase: golden_hour

# c) wysokość nad horyzontem
condition:
  type: sun
  above: 10
  below: 25
```

Reguła: dokładnie jeden z zestawów `{after, before}`, `{phase}`, `{above, below}`.
Walidator Cerberusa pilnuje tego przez `excludes`.

Kształt `after`/`before` celowo powiela warunek `time` — ten sam model myślowy,
ten sam układ pól w UI, ta sama obsługa przejścia przez północ (okno
`sunset → sunrise` przechodzi przez północ i musi działać tak samo jak `22:00 → 06:00`).

`*_offset` przyjmuje wartości ujemne, czego obecne `positive_time_period` nie umie —
potrzebny nowy koercer `signed_time_period` w `boneio/core/config/yaml_util.py`
(obok `_normalize_coerce_positive_time_period`, linia 722). Zakres ±12 h; większy
offset przestaje być „odniesieniem do zachodu" i lepiej wtedy użyć `type: time`.

### 4.2 Wykonanie

`_SunCondition` w `action_conditions.py`, symetryczne do `_TimeCondition`:

```python
class _SunCondition:
    __slots__ = ("mode", "after", "after_offset", "before", "before_offset",
                 "phase", "above", "below", "_sun")

    def evaluate(self, now: datetime) -> bool: ...
```

- W chwili prekompilacji zapamiętujemy nazwy kotwic i offsety (bez liczenia czasów —
  config ładuje się raz, a urządzenie chodzi miesiącami).
- W chwili oceny pytamy współdzielony `SunProvider` o **cache dnia**: słownik 18 kotwic
  dla `now.date()`, liczony leniwie przy pierwszym trafieniu w nowy dzień.
  Warunek nie liczy efemeryd — czyta dwie daty ze słownika i porównuje.
- Tryb `above`/`below` woła `solar_position` z cache'em 60-sekundowym
  (Słońce przesuwa się o ~0.25°/min; dla progów co najmniej stopniowych to poniżej
  rozdzielczości jakiegokolwiek sensownego zastosowania).

`SunProvider` (nowy `boneio/core/manager/sun.py`) trzyma lokalizację, cache dnia,
i unieważnia go przy zmianie configu, strefy czasowej albo skoku zegara.

### 4.3 Strefy czasowe — jedna zmiana na hot-path

Dziś `manager.py:906` robi `now_dt = datetime.now()` — czas naiwny, lokalny.
Kotwice słoneczne rodzą się jako aware UTC. Porównywanie ich z naiwnym lokalnym
wymagałoby konwersji przy każdym naciśnięciu przycisku i byłoby niejednoznaczne
w godzinie cofnięcia zegara jesienią.

Zmiana: `now_dt = datetime.now().astimezone()`. Aware lokalny. Koszt jednorazowy
na batch, `_TimeCondition` (`.time()`) i `_DateCondition` (`.month`, `.day`) działają
bez modyfikacji, a `_SunCondition` porównuje aware z aware. To jedyna modyfikacja
istniejącej logiki w całej fazie 2.

### 4.4 Awarie i przypadki brzegowe

| Sytuacja | Zachowanie |
|---|---|
| Brak sekcji `location:` | Warunek zwraca `True` (spójnie z resztą: błąd configu nie blokuje akcji) **i** `webui/action_validation.py` zgłasza twardy błąd w panelu, żeby to nigdy nie doszło do runtime'u po cichu |
| Dzień polarny (Słońce nie schodzi poniżej progu) | Kotwica = `None`; okno `sunrise→sunset` obejmuje całą dobę, `civil_dusk→civil_dawn` jest puste |
| Noc polarna | Odwrotnie: okno „dzienne" puste, „nocne" na całą dobę |
| Złota godzina na wysokich szerokościach (h nigdy nie sięga +6°) | `golden_hour_*_end` = `None` → koniec okna przypada na `solar_noon` |
| Zegar niezsynchronizowany po starcie | BBB nie ma podtrzymywanego RTC. `SunProvider` nie liczy nic, dopóki `year < 2025`; loguje raz i próbuje ponownie po synchronizacji NTP. Warunek wstępny domknięty: od 1.6.9 można wskazać własny serwer NTP w sieci lokalnej — patrz `docs/TIMEZONE_NTP.md` |
| Zmiana strefy czasowej z panelu | Unieważnienie cache dnia (`SunProvider.invalidate()`) w handlerze `POST /api/system/timezone` |
| Przejście DST | Niewidoczne — liczymy w UTC, konwertujemy przez `ZoneInfo` z systemu |

---

## 5. Encja `sun` i sensory (faza 3)

Wzorzec jak `virtual_energy_sensor` (`boneio/components/sensor/virtual_energy.py`,
rejestracja w `boneio/core/manager/sensors.py:989`).

| Encja | Typ | Aktualizacja |
|---|---|---|
| `sun_elevation` | sensor `°` | `update_interval`, domyślnie 60 s |
| `sun_azimuth` | sensor `°` | jw. |
| `sun_phase` | sensor tekstowy | przy zmianie fazy |
| `sun_next_sunrise`, `sun_next_sunset`, `sun_next_dawn`, `sun_next_dusk` | sensor `timestamp` | raz na dobę + po zdarzeniu |
| `sun_above_horizon` | binary_sensor | przy przejściu |

Dzięki `sun_above_horizon` warunek `type: state` z `entity: binary_sensor` zadziała
bez żadnych zmian, a Home Assistant dostaje encje zgodne ze swoją integracją `sun`.

W panelu: kafelek „Słońce" z dzisiejszymi godzinami i bieżącą wysokością — to również
najtańszy sposób, żeby użytkownik zweryfikował, czy dobrze wpisał współrzędne.

---

## 6. Wyzwalacze słoneczne (faza 4)

Bez tego „zamknij rolety o zachodzie" nadal wymaga naciśnięcia przycisku.
Nowa sekcja najwyższego poziomu:

```yaml
schedule:
  - id: rolety_zachod
    name: "Rolety — zachód"
    enabled: true
    trigger:
      type: sun            # sun | time
      event: sunset
      offset: "-15min"
      jitter: "10min"      # opcjonalny losowy rozrzut, symulacja obecności
    conditions:            # ten sam schemat co w akcjach
      mode: and
      list:
        - type: date
          after: "10-01"
          before: "04-30"
    actions:
      - action: cover
        boneio_cover: salon
        action_cover: CLOSE
```

Runtime — `SunScheduler`:
- o lokalnej północy, przy starcie i po unieważnieniu cache liczy dzisiejsze czasy odpalenia
  i uzbraja `async_track_point_in_time` (`core/events/bus.py:372`),
- zdarzenie nieistniejące danego dnia (polarne) → wpis pominięty z logiem raz na dobę,
- **pominięte odpalenia po restarcie**: `on_missed: skip | run`, domyślnie `skip`,
  z oknem tolerancji 15 min (restart o 21:50 przy zachodzie 21:45 domyka rolety;
  restart rano już nie),
- `jitter` losowany raz na dobę, nie przy każdym odpaleniu — inaczej rolety „drgają".

Warunki z sekcji `conditions` przechodzą przez istniejące `precompile_conditions`
bez jednej linii zmian. To jest właśnie powód, dla którego faza 2 idzie przed fazą 4.

---

## 7. Frontend

| Plik | Zmiana |
|---|---|
| `ActionFields/ActionConditions.tsx:47` | `CONDITION_TYPES` += `'sun'`; nowy blok pól: selektor trybu (okno / faza / wysokość) + selektory kotwic pogrupowane (Podstawowe · Zmierzch · Fotograficzne) + pola offsetu |
| `ActionFields/helpers.ts:68` | `validateCondition`: wymagalność pól per tryb, zakres offsetu ±12 h, zakres wysokości −90..90 |
| `components/ActionDetails.tsx:57` | `ConditionBadges`: `🌅 wschód −30min → zmierzch cyw.` |
| `SystemStateComponents/` | nowa `LocationSection.tsx` obok `TimezoneSection.tsx`, z podglądem dzisiejszych godzin (weryfikacja współrzędnych na oko) |
| `locales/pl/common.json`, `locales/en/common.json` | `event_form.condition_type_sun`, nazwy 18 kotwic, 7 faz, komunikaty walidacji |

Podgląd godzin w `LocationSection` liczy backend (`GET /api/sun/today`) — nie duplikujemy
algorytmu w TypeScripcie. Jedno źródło prawdy, jeden zestaw testów.

---

## 8. Testy

- `tests/unit/test_sun_engine.py`
  - siatka referencyjna NOAA: Warszawa, Tromsø (69.6°N — dzień i noc polarna),
    Quito (równik), Sydney (półkula południowa), dni przesileń i równonocy,
  - porównanie z `astral` (zależność wyłącznie testowa) — tolerancja 60 s,
  - monotoniczność kotwic w obrębie doby,
  - dni przejścia DST w `Europe/Warsaw`.
- `tests/unit/test_sun_conditions.py`
  - przejście przez północ (`sunset → sunrise`),
  - offsety ujemne i dodatnie,
  - brak `location:` → `True` + zalogowany błąd,
  - polarne `None` w obu kierunkach,
  - `above`/`below` na granicy progu.
- `tests/unit/test_sun_scheduler.py` (faza 4) — pominięte odpalenia, jitter, północna przeliczka.

---

## 9. Fazy i kolejność

| Faza | Zakres | Samodzielnie wypuszczalna? | Szacunek |
|---|---|---|---|
| **S1** ✅ | `boneio/core/utils/sun.py` + testy referencyjne. Zero integracji. | Zrobione — patrz `docs/SUN.md` | — |
| **S2** ✅ | Sekcja `location:` + `SunProvider` + `LocationSection.tsx` + `GET /api/sun/today` | Zrobione — Ustawienia → Urządzenie → Lokalizacja | — |
| **S3** ✅ | Warunek `type: sun` (schemat, prekompilacja, ścieżka generyczna, walidacja, UI, i18n) | Zrobione — edytor akcji, trzy tryby | — |
| **S4** ✅ | Encje/sensory `sun_*` + MQTT + discovery HA + kafelek | Zrobione — 6 encji, plus mapa do wyboru współrzędnych | — |
| **S5** ✅ | Sekcja `schedule:` + `SunScheduler` + UI harmonogramów | Zrobione — patrz `docs/SCHEDULES.md` | — |

**Wszystkie fazy S1–S5 są zrobione.** Silnik liczy 18 kotwic i fazy, zgadza się z `astral`
co do 41 s przez cały rok dla ośmiu miast na obu półkulach, obsługuje dzień i noc
polarną oraz wysokość n.p.m. Na tym stoi sekcja `location:`, `SunProvider`
(cache dnia, rozpoznanie strefy czasowej, blokada przy nieustawionym zegarze),
`GET /api/sun/today` i strona Lokalizacja w panelu. 91 testów, dokumentacja
w `docs/SUN.md`. Wybrany zakres: **S1–S3, z opcją rozszerzenia do S5.**

Warunek `type: sun` ma trzy kształty (okno między kotwicami z przesunięciami,
faza, pasmo wysokości), wzajemnie się wykluczające i wymuszone zarówno przez
Cerberusa przy ładowaniu, jak i przez walidator panelu przy zapisie. Na hot-pathu
kosztuje dwa odczyty ze słownika i dwa porównania dat.

S4 dokłada sześć encji (`sun_elevation`, `sun_azimuth`, `sun_phase`,
`sun_above_horizon`, `sun_next_sunrise`, `sun_next_sunset`) na wspólnym
`BaseSensor`, z odświeżaniem co 60 s i pełnym discovery HA. Powstają tylko
wtedy, gdy jest sekcja `location:`, i milczą, gdy wartości nie da się poznać —
przy nieustawionym zegarze albo w sezonie polarnym — zamiast publikować null
albo zachód słońca policzony dla 1970 roku.

Jedyna zmiana w istniejącej logice wykonania: `manager.py` liczy teraz
`datetime.now().astimezone()` zamiast `datetime.now()`. Kotwice słoneczne rodzą
się jako aware UTC, a porównanie ich z naiwnym czasem lokalnym byłoby
dwuznaczne w godzinie cofnięcia zegara. `_TimeCondition` i `_DateCondition`
działają bez zmian.

S5 dokłada sekcję `schedule:` — akcje odpalające się same, o godzinie zegarowej
albo w momencie wyznaczonym przez słońce, z przesunięciem, losowym rozrzutem,
filtrem dni i nadrabianiem pominiętych odpaleń. Plan jest przeliczany co minutę
z bieżącego zegara, bo NTP przestawia czas przy starcie, a timer uzbrojony przed
przestawieniem celuje w zły moment. Panel: Ustawienia → Sterowanie →
Harmonogramy, z „następnym odpaleniem" i przyciskiem „Odpal teraz" — harmonogram
to jedyna rzecz w boneIO, której nie da się sprawdzić naciśnięciem przycisku.

S1→S2→S3 to minimalna ścieżka do użytecznej funkcji. S5 jest największy i jako jedyny
wprowadza nową sekcję konfiguracji z własnym cyklem życia — warto go trzymać osobno
od reszty, także dlatego, że jako jedyny może coś zrobić bez udziału człowieka.

---

## 10. Decyzje

1. **Zakres 1.6.x** — ✅ S1–S3, z opcją rozszerzenia do S5.
2. **Silnik** — ✅ własny moduł; `astral` został zależnością **wyłącznie testową**
   i służy do kontroli poprawności.
3. **Sekcja harmonogramu** — ✅ osobna `schedule:`. `event:` jest przywiązane do
   pinów GPIO (`check_with: input_id_exists`), więc dokładanie tam wyzwalaczy
   czasowych zrobiłoby z niej dwie rzeczy naraz.
4. **Mapa do wyboru współrzędnych** — jest, ale **domyślnie wyłączona**
   (`web.security.map_tiles`). Włączenie dokłada serwery kafelków
   OpenStreetMap do dyrektywy `img-src` w CSP panelu, a to realne poluzowanie:
   adres obrazka jest kanałem wychodzącym, więc ktoś, kto ma już wykonanie
   skryptu w panelu, mógłby upchnąć kilkaset bajtów w ścieżce kafelka i
   odczytać je z cudzego access loga. `connect-src` zostaje `'self'`, reszta
   polityki się nie rusza — jest na to test. Bez zależności: `TilePicker.tsx`
   to ~200 linii matematyki Web Mercator, Leaflet ważyłby 45 kB za funkcje,
   których ta strona nie używa. Kafelki pobiera **przeglądarka**, nie sterownik,
   więc działa to na instalacji bez internetu — o ile ma go komputer, z którego
   otwierasz panel.
5. **Zachowanie przy braku lokalizacji** — warunek słoneczny bez sekcji
   `location:` przepuszcza akcję (fail-open, jak każdy inny warunek przy błędzie
   konfiguracji) i loguje raz. Ryzyko jest realne: taki warunek niczego nie
   bramkuje, a wygląda na działający. Dlatego panel **odmawia zapisu** akcji
   z warunkiem słonecznym, dopóki współrzędne nie są ustawione. Alternatywa
   (fail-closed) oznaczałaby, że zdjęcie sekcji `location:` unieruchamia
   przyciski w całym domu — gorzej.
6. **Geolokalizacja z przeglądarki** — świadomie pominięta. Wymagałaby
   bezpiecznego kontekstu (panel po HTTP w LAN go nie ma) **oraz** poluzowania
   `Permissions-Policy: geolocation=()` z `webui/security_headers.py`, czyli
   cofnięcia jednej z poprawek po pentescie. Zamiast tego jest uzupełnianie
   ze strefy czasowej. Do przemyślenia, gdy panel będzie standardowo po HTTPS.

## 11. Powiązane: czas systemowy (1.6.9)

Cała warstwa słoneczna jest dokładnie tak dobra jak zegar urządzenia, a BBB nie
ma podtrzymywanego RTC. Przy okazji S1 doszła więc możliwość wskazania własnego
serwera NTP w sieci lokalnej (`/etc/systemd/timesyncd.conf.d/boneio.conf`,
zapisywany przez `boneio-system ntp-set`, dwa nowe czasowniki w helperze,
migracja 1.6.9). Bez tego instalacja bez dostępu do internetu nigdy nie
synchronizuje zegara, a każdy warunek czasowy jest tam fikcją.
Szczegóły: `docs/TIMEZONE_NTP.md`.
