---
description: Procedura Release dla app_black
---

## Procedura Release dla app_black

Gdy użytkownik powie "wydaj vX.Y.Z" lub "wydaj vX.Y.ZdevN", wykonaj:

### 1. Zmień wersję w version.py

Plik: `boneio/version.py`

```python
__version__ = "X.Y.Z"  # lub "X.Y.ZdevN"
```

### 2. Commit + tag + push

```bash
git add -A
git commit -m "release vX.Y.Z"
git tag vX.Y.Z
git push origin <current-branch> --tags
```

### 3. Co dzieje się automatycznie (GitHub Actions):

1. `auto-release.yml` — tworzy GitHub Release z changelogiem z commitów
2. `publish-to-pypi.yaml` — buduje paczkę i publikuje na PyPI (triggeruje się na push taga v\*)

### Release Notes

Automatyczny changelog jest generowany z commit messages. Reguły:

#### Dla stabilnych release'ów (np. v1.3.0):
- Porównuje z **poprzednim stabilnym tagiem** (pomija dev/alpha/beta/rc tagi)
- Dzięki temu changelog obejmuje **cały cykl dev** — wszystkie commity od np. v1.2.0 do v1.3.0
- Commity są **grupowane** wg prefixu:
  - `feat/add/new/implement` → ✨ New Features
  - `fix/bug/patch/hotfix` → 🐛 Bug Fixes
  - `refactor/clean/rename` → ♻️ Refactoring
  - `doc/readme` → 📝 Documentation
  - inne → 📦 Other Changes
- Commity `release v*/bump version` są automatycznie pomijane

#### Dla dev release'ów (np. v1.3.0dev20):
- Porównuje z **bezpośrednio poprzednim tagiem** (dowolny typ)
- Prosta lista zmian bez kategoryzacji

#### Ręczne release notes (opcjonalne):
- Jeśli w katalogu głównym repo istnieje plik `RELEASE_NOTES.md`, zostanie użyty jako treść release'u zamiast auto-generowanego changelogu
- Przydatne do stabilnych wydań, gdzie chcesz opisowy changelog
- Plik możesz potem usunąć po release'ie

### Konwencje commit messages:

- Używaj opisowych prefixów: `feat:`, `fix:`, `refactor:`, `docs:` dla lepszego auto-grupowania
- Breaking changes: prefix `BREAKING:` w commit message
- Wersje dev/prerelease: `vX.Y.ZdevN` — automatycznie oznaczane jako prerelease na GitHub

### WAŻNE:

- Krok "Inject Cloud API Secret" (secrets.py) jest zakomentowany jako TODO w publish-to-pypi.yaml
- Plik boneio/core/cloud/secrets.py istnieje TYLKO na branchu dev-debian13-v2 (PWA)
- Odkomentować dopiero gdy PWA branch zostanie zmerge'owany do dev-debian13

### Branch:

- `dev-debian13` — główny branch deweloperski (Python 3.13, Debian 13)
- `dev-debian13-v2` — branch z cloud registration/PWA
- `main` — stabilny

### Wymagane secrety GitHub:

- `PYPI_API_TOKEN`
- `BONEIO_MASTER_SECRET` (na przyszłość, gdy PWA merge)
