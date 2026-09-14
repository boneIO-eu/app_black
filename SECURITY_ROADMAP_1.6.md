# Roadmapa bezpieczeństwa boneIO Black → 1.6.x

Podstawa: raport pentestowy 1.5.0 (`Pobrane/boneio_raport_1.5.0/`), 16 ustaleń F-01…F-16.
Zasada: każda poprawka wdrażana jako **nowa funkcja** (nie łata w ukryciu), po kolei, każde wdrożenie samodzielnie wypuszczalne w 1.6.x.

## Mapowanie wdrożeń na ustalenia

| # | Wdrożenie (nowa funkcja) | Łata (findings) | Warstwa |
|---|---|---|---|
| 1 | **Kreator pierwszego uruchomienia (Onboarding)** — wizard: powitanie → utworzenie konta admina (hash) → opcjonalny import starego configu / restore backupu → podsumowanie | F-03 (koniec plaintext), F-14 (właściciel ustawia creds pierwszy), część F-08 | backend + frontend |
| 2 | **Role: admin + read-only (RBAC)** — konto/rola „viewer" tylko do odczytu; JWT niesie rolę; middleware wymusza metodę wg roli; panel blokuje akcje dla viewera | F-02, F-14, fundament reszty | backend + frontend |
| 3 | **Twardnienie logowania** — rate-limit + lockout na `/api/login` i SSH-owy odpowiednik, login nie wydaje tokenu dla losowych danych, nagłówki bezpieczeństwa (HSTS/CSP/X-Frame/Permissions-Policy) | F-06, F-08, F-13 | backend |
| 4 | **Ochrona sekretów w API** — maskowanie haseł w `GET /api/config` i logach | F-03, część F-12 | backend |
| 5 | **Node-RED adminAuth** — wstrzyknięcie `adminAuth` spiętego z kontem admina boneIO | F-01 (RCE) | backend + provisioning |
| 6 | **Ochrona SSRF** — walidacja host/port w `discover-wled`/`discover-esphome`: blokada loopback/link-local/prywatnych + wymóg roli admin | F-15 | backend |
| 7 | **Ochrona CSRF** — sprawdzanie Origin/Referer lub token na operacjach zmieniających stan | F-07 | backend |
| 8 | **Twardnienie kodu i systemu** — `O_EXCL`/`mkstemp` w `timezone_sudoers.py` (F-09), rejestracja `!secret` w migracji `v4_wled_cache.py` (F-16); poza-appowe (obraz/provisioning): sudo (F-04), domyślne MQTT (F-05), TLS cert (F-10), perms `/etc/mosquitto/passwd` (F-11) | F-04,05,09,10,11,16 | kod + obraz |

## Decyzje przekrojowe

### Wymuszenie konta (dotyczy #1 i #2)
Reguła **oparta na stanie, nie na wersji**: każde boneIO >= 1.6, które wystartuje bez kont i bez jawnej flagi
`web.auth.allow_anonymous: true`, wymusza kreator i **zamyka API**. Działa identycznie dla świeżego flasha,
1.5->1.6 i 1.5->1.7, więc nie zakłada kolejności aktualizacji. Bez przycisku "Pomiń" w UI: ostrzeżenie to
komunikat, nie mechanizm kontroli, a CRA wymaga bezpiecznej **konfiguracji domyślnej**. Furtka istnieje, ale
w `config.yaml` — świadoma edycja przez SSH to odstępstwo eksperta, a nie domyślne zachowanie.
Odkrywalność dla kogoś, kto przeskoczył wersje: komunikat na **OLED** ("Setup required") + WARNING w logu
z gotową linijką do wklejenia.

### Domyślne poświadczenia w obrazie (#8)
`black_debian_images/scripts/build_image_usb.sh:174` wypala to samo hasło SSH na każdym urządzeniu
(`chpasswd`), a `setup_boneio.sh:403` to samo hasło MQTT (`boneio123`, F-05). To **universal default
password** — wprost zakazane przez EN 303 645 par. 5.1 i PSTI, i opublikowane w `UPDATE.md`.
Kierunek: SSH domyślnie **bez logowania hasłem** (`PasswordAuthentication no`), klucz lub hasło ustawiane
z panelu przez zalogowanego admina. Plan B: losowe hasło per urządzenie pokazywane na OLED **na żądanie**
i tylko dopóki urządzenie jest nieskonfigurowane, rotowane po utworzeniu konta admina.
**Nie** wyprowadzać hasła z numeru seryjnego — seryjny jest nadrukowany i rozgłaszany przez MQTT discovery,
więc to domyślne hasło w przebraniu.

## Kolejność rekomendowana
1 → 2 → 3 → 4 → reszta. Wdrożenia 1–2 to fundament auth/RBAC, na którym stoi reszta.

## Zrobione

### 1. Kreator pierwszego uruchomienia
- `boneio/core/auth/` — model konta z rolami, haszowanie scrypt (stdlib, bez nowej zależności), magazyn `users.json` zapisywany atomowo z uprawnieniami 0600 obok `config.yaml`.
- Migracja starego `web.auth` przy starcie: konto przenoszone do `users.json` jako hash, `config.yaml` nietykany, ostrzeżenie w logu o usunięciu sekcji. Krótkie stare hasło jest migrowane mimo polityki — odrzucenie zamieniłoby aktualizację w zablokowanie właściciela.
- `GET /api/onboarding/status`, `POST /api/onboarding/admin` (odmawia z 409, gdy admin już istnieje), `needs_onboarding` w `/api/init`.
- `AuthMiddleware` instalowany **bezwarunkowo** i bramkowany przez `is_auth_required()` — wcześniej był dodawany tylko, gdy `web.auth` istniało, więc urządzenie skonfigurowane kreatorem zostałoby otwarte aż do restartu.
- `/api/login` uwierzytelnia przez `users.json` i wkłada rolę do tokenu.
- Kreator w UI: 4 kroki, import backupu przez istniejące `POST /api/config/restore`, tłumaczenia PL/EN.
- Testy: 100 nowych (backend) + 6 (frontend).

**Domknięte przy okazji:** F-08 dla urządzeń z kontem (koniec tokenu na dowolne dane), przejęcie z F-14 przez nieuwierzytelnione ustawienie creds, F-03 w części dotyczącej `config.yaml` (konta wyprowadzone z pliku, więc backup i eksport nie mają czego wyciekać).

**Świadomie zostawione:** urządzenie, które **nigdy** nie miało poświadczeń, dalej ma otwarte API (F-02) — to zachowanie sprzed 1.6 i domyka je wdrożenie #2.

### 2. Role admin/viewer + domknięcie F-02
- **F-02 domknięte.** Urządzenie bez konta odmawia API (403 `setup_required`) zamiast obsługiwać wszystkich. Reguła **stanowa, nie wersyjna** — działa tak samo dla świeżego flasha, 1.5->1.6 i 1.5->1.7.
- Furtka: `web.auth.allow_anonymous: true` **tylko w config.yaml**, z WARNING-iem przy każdym starcie i trwałym banerem w UI. Działa wyłącznie na urządzeniu bez kont — skopiowana flaga nie odblokuje urządzenia, które ma użytkowników.
- Polityka ról w `boneio/webui/middleware/policy.py` jako czytelna tabela. Viewer: podgląd + sterowanie (wyjścia, rolety, nawadnianie, termostaty, alarmy). Admin: wszystko. Trasa nieopisana w polityce wymaga admina (domyślnie zamknięte). Każda reguła wiąże **metodę** ze ścieżką.
- Konta: `/api/accounts` (zarządzanie, admin) i `/api/account` (self-service — viewer może zmienić własne hasło, podając stare).
- UI: ekran kont, ukrycie pozycji administracyjnych przed viewerem, baner trybu anonimowego.
- OLED + log mówią `SETUP REQUIRED` na starcie nieskonfigurowanego urządzenia.
- Testy: 1227 lokalnie, 110 na realnym ARM, 26/26 asercji HTTP na sterowniku.

**Domknięte przy okazji:** część F-12 — pobieranie archiwów configu (pakują `secrets.yaml`) i surowy edytor plików wymagają teraz admina.

**Świadomie zostawione:** viewer widzi `GET /api/config`, bo panel tego potrzebuje — maskowanie sekretów to wdrożenie #4.

### 3. Twardnienie logowania (F-06, F-13)
- **F-06 domknięte dla web.** `/api/login` throttlowany: 10 prób / 5 min, liczone **równolegle po IP i po koncie** (samo IP jest ślepe za reverse proxy, samo konto ślepe na rozsiew jednego hasła po wielu nazwach). Throttle, **nie lockout** — okno się wysuwa, więc napastnik może co najwyżej kazać właścicielowi poczekać. `429` zwracany **przed** sprawdzeniem poświadczeń i identyczny niezależnie od tego, czy konto istnieje. Udane logowanie zeruje liczniki. Uogólniono istniejący `sudo_rate_limiter` zamiast pisać drugi (raport sam to wytknął).
- **F-13 domknięte.** Doszły `Content-Security-Policy`, `Permissions-Policy` i warunkowy `Strict-Transport-Security`.
  - `X-Frame-Options` **nadal niewysyłane** — nie potrafi wskazać dozwolonego origin, więc nie wyrazi przypadku HA ingress. Zamiast tego CSP `frame-ancestors` jako `web.security.frame_ancestors`, **domyślnie nieustawione**, żeby nie zepsuć istniejących osadzeń.
  - HSTS z `max-age=86400`, nie rocznym: przeglądarka ignoruje HSTS z niezweryfikowanego połączenia, więc self-signed nic nie traci; ryzyko jest odwrotne — urządzenie z rejestracją w chmurze ma prawdziwy certyfikat, a po jej wyłączeniu ta sama nazwa wraca na self-signed i roczny pin zablokowałby wejście bez możliwości kliknięcia dalej.
  - CSP zweryfikowane **testem A/B na sprzęcie**: edytor YAML zachowuje się identycznie z polityką i bez niej.

**Przeniesione do #8:** throttling SSH (`sshd` / fail2ban) — to konfiguracja obrazu w `black_debian_images`, nie aplikacji.

**Uwaga:** F-08 zostało domknięte już w #1 dla urządzeń z kontem; otwarta zostaje tylko ścieżka urządzenia bez żadnych poświadczeń, czyli stan anonimowy opisany w #2.

## Status
- [x] 1. Onboarding — **zrobione** (gałąź `feature/onboarding-wizard`, 1.6.0.dev1)
- [x] 2. Role admin/read-only — **zrobione** (gałąź `feature/rbac-admin-viewer`)
- [x] 3. Twardnienie logowania — **zrobione w aplikacji** (gałąź `feature/login-hardening`); część SSH przeniesiona do #8
- [ ] 4. Ochrona sekretów
- [ ] 5. Node-RED adminAuth
- [ ] 6. SSRF
- [ ] 7. CSRF
- [ ] 8. Twardnienie kodu/systemu
