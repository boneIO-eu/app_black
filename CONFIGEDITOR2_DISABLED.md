# ConfigEditor2 - Tymczasowo Wyłączony

## Status
ConfigEditor2 (UISettings) jest **tymczasowo wyłączony** z powodu problemów z walidacją JSON Schema i kompatybilnością RJSFSchema.

## Co zostało zrobione
1. **Ukryto z nawigacji** - pozycja "Settings" w menu jest zakomentowana
2. **Zachowano routing** - ścieżki `/settings` i `/settings/:section` nadal istnieją
3. **Dodano komentarze** - wyjaśniające dlaczego jest wyłączone

## Problemy do rozwiązania
- Błędy walidacji JSON Schema
- Niezgodność typów między RJSFSchema a danymi
- Problemy z konwersją typów (string/number/boolean)
- Problemy z zagnieżdżonymi strukturami schema

## Jak ponownie włączyć

### 1. Przywrócenie nawigacji
W pliku `frontend/src/components/Navigation.tsx` odkomentuj linię:
```typescript
// { path: '/settings', icon: FaCode, label: 'Settings', experimental: true }, // Temporarily disabled due to JSON Schema issues
```

### 2. Usunięcie komentarzy z routingu
W pliku `frontend/src/App.tsx` usuń komentarze:
```typescript
{/* ConfigEditor2 (UISettings) - Temporarily disabled due to JSON Schema issues */}
{/* TODO: Re-enable when JSON Schema validation problems are resolved */}
```

### 3. Aktualizacja dokumentacji
W pliku `frontend/src/components/UISettings/UISettings.tsx` usuń z komentarza JSDoc:
```typescript
* CURRENTLY DISABLED: This component is temporarily disabled due to JSON Schema validation
* issues and RJSFSchema compatibility problems. The routes still exist but the navigation
* menu item is commented out. Can be re-enabled when schema issues are resolved.
```

## Pliki do sprawdzenia przy ponownym włączaniu
- `frontend/src/components/UISettings/UISettings.tsx` - główny komponent
- `frontend/src/components/UISettings/ArrayTableWidget.tsx` - widget do tabeli
- `frontend/src/components/UISettings/helpers/` - funkcje pomocnicze
- `boneio/webui/schema_converter.py` - generator schema po stronie backendu

## Testowanie
Po ponownym włączeniu przetestuj:
1. Ładowanie sekcji konfiguracji
2. Wyświetlanie formularzy
3. Walidację danych
4. Zapisywanie zmian
5. Konwersję typów (szczególnie timeperiod, enum, boolean)

## Kontakt
Jeśli potrzebujesz pomocy przy ponownym włączaniu, skontaktuj się z deweloperem.
