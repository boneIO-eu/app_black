# BoneIO Black Image Preparation Scripts

Skrypty do przygotowania różnych wersji obrazów BoneIO Black dla BeagleBone Black.

## Dostępne wersje urządzeń

- **32x10A** - 32 wyjścia 10A (domyślna wersja)
- **24x16A** - 24 wyjścia 16A
- **Cover** - Wersja do rolet
- **Cover Mix** - Wersja mieszana z roletami

## Wymagania

- Linux z uprawnieniami root (do montowania obrazów)
- Narzędzia: `losetup`, `mount`, `umount`

## Szybki start

### Metoda 1: Automatyczne montowanie i przygotowanie

```bash
# 1. Nadaj uprawnienia wykonywania
chmod +x scripts/*.sh

# 2. Zamontuj obraz (wymaga sudo)
sudo ./scripts/mount_image.sh boneio-black.img /mnt/boneio

# 3. Przygotuj wersję (np. Cover Mix)
./scripts/prepare_image.sh /mnt/boneio "Cover Mix"

# 4. Odmontuj obraz (wymaga sudo)
sudo ./scripts/umount_image.sh /mnt/boneio

# 5. Wgraj obraz na kartę SD/eMMC
```

### Metoda 2: Ręczne montowanie

```bash
# 1. Zamontuj obraz ręcznie
sudo losetup -fP boneio-black.img
sudo mount /dev/loop0p2 /mnt/boneio  # Dostosuj partition number

# 2. Przygotuj wersję
./scripts/prepare_image.sh /mnt/boneio "24x16A"

# 3. Odmontuj
sudo umount /mnt/boneio
sudo losetup -d /dev/loop0
```

## Szczegółowy opis skryptów

### prepare_image.sh

Główny skrypt do przygotowania obrazu dla konkretnej wersji urządzenia.

**Użycie:**
```bash
./prepare_image.sh <mount_point> <device_type>
```

**Parametry:**
- `mount_point` - Punkt montowania obrazu (np. `/mnt/boneio`)
- `device_type` - Typ urządzenia (opcjonalny, domyślnie `32x10A`)

**Przykłady:**
```bash
# Wersja 32x10A (domyślna)
./prepare_image.sh /mnt/boneio
./prepare_image.sh /mnt/boneio "32x10A"

# Wersja 24x16A
./prepare_image.sh /mnt/boneio "24x16A"

# Wersja Cover
./prepare_image.sh /mnt/boneio "Cover"

# Wersja Cover Mix
./prepare_image.sh /mnt/boneio "Cover Mix"
```

**Co robi skrypt:**
1. Znajduje katalog konfiguracyjny w zamontowanym obrazie
2. Tworzy backup istniejącej konfiguracji
3. Kopiuje odpowiednie pliki konfiguracyjne z `boneio/example_config/<device_type>/`
4. Aktualizuje `device_type` i `name` w `config.yaml`
5. Ustawia odpowiednie uprawnienia

### mount_image.sh

Pomocniczy skrypt do montowania obrazu BeagleBone Black.

**Użycie:**
```bash
sudo ./mount_image.sh <image_file> <mount_point>
```

**Przykład:**
```bash
sudo ./mount_image.sh boneio-black.img /mnt/boneio
```

### umount_image.sh

Pomocniczy skrypt do odmontowywania obrazu.

**Użycie:**
```bash
sudo ./umount_image.sh <mount_point>
```

**Przykład:**
```bash
sudo ./umount_image.sh /mnt/boneio
```

## Struktura katalogów konfiguracyjnych

Skrypt automatycznie szuka katalogu konfiguracyjnego w następujących lokalizacjach:
- `/home/debian/boneio/config`
- `/opt/boneio/config`
- `/root/boneio/config`

## Backup

Przed każdą zmianą konfiguracji tworzony jest automatyczny backup:
```
<config_dir>.backup.YYYYMMDD_HHMMSS
```

Przykład: `/home/debian/boneio/config.backup.20260106_181500`

## Rozwiązywanie problemów

### Błąd: "Could not find boneio config directory"

Obraz może mieć inną strukturę katalogów. Sprawdź ręcznie:
```bash
find /mnt/boneio -name "config.yaml" -type f
```

I dostosuj ścieżkę w skrypcie `prepare_image.sh` (zmienna `CONFIG_PATHS`).

### Błąd: "Permission denied"

Upewnij się, że:
1. Skrypty montowania/odmontowania uruchamiasz z `sudo`
2. Masz uprawnienia do zapisu w katalogu konfiguracyjnym

### Błąd: "Device or resource busy"

Odmontuj wszystkie zamontowane partycje:
```bash
sudo umount /mnt/boneio
sudo losetup -D  # Usuń wszystkie loop devices
```

## Workflow produkcyjny

Przykładowy workflow do przygotowania wielu obrazów:

```bash
#!/bin/bash
# Przygotuj wszystkie wersje obrazów

VERSIONS=("32x10A" "24x16A" "Cover" "Cover Mix")
BASE_IMAGE="boneio-black-base.img"

for version in "${VERSIONS[@]}"; do
    # Skopiuj bazowy obraz
    version_normalized=$(echo "$version" | tr ' ' '_' | tr '[:upper:]' '[:lower:]')
    output_image="boneio-black-${version_normalized}-v1.0.0.img"
    
    echo "Preparing $version -> $output_image"
    cp "$BASE_IMAGE" "$output_image"
    
    # Zamontuj
    sudo ./scripts/mount_image.sh "$output_image" /mnt/boneio
    
    # Przygotuj wersję
    ./scripts/prepare_image.sh /mnt/boneio "$version"
    
    # Odmontuj
    sudo ./scripts/umount_image.sh /mnt/boneio
    
    echo "✓ $output_image ready"
done

echo "All images prepared!"
```

## Notatki

- Domyślna wersja w obrazie bazowym to **32x10A**
- Każda wersja ma dedykowane pliki konfiguracyjne w `boneio/example_config/`
- Skrypt zachowuje backup przed każdą zmianą
- Po przygotowaniu obrazu można go wgrać na kartę SD lub bezpośrednio na eMMC BeagleBone Black
