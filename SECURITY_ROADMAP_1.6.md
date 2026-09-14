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

## Status
- [x] 1. Onboarding — **zrobione** (gałąź `feature/onboarding-wizard`, 1.6.0.dev1)
- [ ] 2. Role admin/read-only
- [ ] 3. Twardnienie logowania
- [ ] 4. Ochrona sekretów
- [ ] 5. Node-RED adminAuth
- [ ] 6. SSRF
- [ ] 7. CSRF
- [ ] 8. Twardnienie kodu/systemu
