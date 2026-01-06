# SystemState.tsx Refactoring

## Problem
Plik `SystemState.tsx` stał się zbyt długi (ponad 2000 linii, 81KB) i nieczytelny. Zawiera zbyt wiele odpowiedzialności w jednym komponencie.

## Rozwiązanie
Refactoring z wydzieleniem logiki do custom hooków i UI do osobnych komponentów.

## Struktura po refactoringu

```
UISettings/
├── hooks/
│   ├── index.ts
│   ├── useSystemUpdate.ts       # Logika aktualizacji systemu
│   ├── useDevicePower.ts        # Logika reboot/shutdown
│   ├── useHostname.ts           # Logika zmiany hostname
│   └── useConfigBackup.ts       # Logika backup/restore
├── sections/
│   ├── index.ts
│   ├── UpdateSection.tsx        # UI sekcji aktualizacji
│   ├── PowerSection.tsx         # UI sekcji reboot/shutdown
│   ├── BackupSection.tsx        # UI sekcji backup
│   └── TurnOffOutputsSection.tsx # UI wyłączania wyjść
└── SystemState.tsx              # Główny komponent (uproszczony)
```

## Custom Hooks

### useSystemUpdate
**Odpowiedzialność:** Zarządzanie aktualizacjami systemu
- Sprawdzanie dostępnych aktualizacji
- Uruchamianie procesu aktualizacji
- Monitorowanie statusu aktualizacji

**API:**
```typescript
const {
  updateInfo,
  isChecking,
  isUpdating,
  updateStatus,
  error,
  checkForUpdates,
  startUpdate,
} = useSystemUpdate();
```

### useDevicePower
**Odpowiedzialność:** Zarządzanie zasilaniem urządzenia
- Restart urządzenia
- Wyłączenie urządzenia

**API:**
```typescript
const {
  isRebooting,
  rebootResult,
  isShuttingDown,
  shutdownResult,
  rebootDevice,
  shutdownDevice,
} = useDevicePower();
```

### useHostname
**Odpowiedzialność:** Zarządzanie hostname urządzenia
- Pobieranie aktualnego hostname
- Zmiana hostname

**API:**
```typescript
const {
  showHostnameSection,
  setShowHostnameSection,
  currentHostname,
  newHostname,
  setNewHostname,
  isChangingHostname,
  hostnameResult,
  fetchCurrentHostname,
  changeHostname,
} = useHostname();
```

### useConfigBackup
**Odpowiedzialność:** Zarządzanie backupami konfiguracji
- Tworzenie backupu
- Przywracanie z backupu
- Lista backupów

**API:**
```typescript
const {
  backups,
  isCreatingBackup,
  isRestoringBackup,
  backupResult,
  fetchBackups,
  createBackup,
  restoreBackup,
} = useConfigBackup();
```

## Section Components

### UpdateSection
**Props:**
- `updateInfo` - informacje o dostępnych aktualizacjach
- `isChecking` - czy trwa sprawdzanie
- `isUpdating` - czy trwa aktualizacja
- `updateStatus` - status procesu aktualizacji
- `error` - błąd
- `onCheckForUpdates` - callback sprawdzania aktualizacji
- `onStartUpdate` - callback uruchomienia aktualizacji

### PowerSection
**Props:**
- `isRebooting` - czy trwa restart
- `rebootResult` - wynik restartu
- `isShuttingDown` - czy trwa wyłączanie
- `shutdownResult` - wynik wyłączania
- `onReboot` - callback restartu
- `onShutdown` - callback wyłączenia

### BackupSection
**Props:**
- `isCreatingBackup` - czy trwa tworzenie backupu
- `isRestoringBackup` - czy trwa przywracanie
- `backupResult` - wynik operacji
- `onCreateBackup` - callback tworzenia backupu
- `onRestoreBackup` - callback przywracania

### TurnOffOutputsSection
**Props:**
- `outputs` - lista wyjść
- `isTurningOff` - czy trwa wyłączanie
- `turnOffProgress` - postęp wyłączania
- `turnOffResult` - wynik operacji
- `onTurnOffAll` - callback wyłączenia wszystkich

## Migracja

### Krok 1: Testowanie nowych komponentów
Nowe komponenty i hooki zostały stworzone w osobnych plikach. Można je testować niezależnie.

### Krok 2: Stopniowa migracja
Oryginalny `SystemState.tsx` pozostaje niezmieniony. Nowa wersja jest w `SystemState.refactored.tsx`.

### Krok 3: Podmiana (gdy gotowe)
```bash
# Backup oryginalnego pliku
mv SystemState.tsx SystemState.old.tsx

# Podmiana na nową wersję
mv SystemState.refactored.tsx SystemState.tsx
```

## Pozostałe sekcje do wydzielenia

Następujące sekcje można dodatkowo wydzielić w przyszłości:
- **MQTT Password Management** - zarządzanie hasłami MQTT
- **SSL/TLS Configuration** - konfiguracja certyfikatów
- **Factory Reset** - reset do ustawień fabrycznych
- **Hardware Versions** - wersje sprzętowe

## Korzyści z refactoringu

1. **Czytelność** - każdy hook/komponent ma jedną odpowiedzialność
2. **Testowalność** - łatwiejsze testowanie jednostkowe
3. **Reużywalność** - hooki mogą być użyte w innych komponentach
4. **Maintainability** - łatwiejsze utrzymanie i rozwój
5. **Performance** - możliwość optymalizacji poszczególnych części

## Uwagi

- Wszystkie nowe pliki są w TypeScript
- Używają istniejących narzędzi (useTranslation, fetch API)
- Zachowują istniejącą logikę biznesową
- Kompatybilne z istniejącym API backendu
