# Optymalizacja czasu ładowania BoneIO - Podsumowanie

## ✅ Zaimplementowane (Etap 1)

### 1. Lazy load WebUI (oszczędność: ~4s)
- **Plik:** `boneio/runner.py`
- **Zmiana:** WebServer importowany tylko gdy web_active=True
- **Oszczędność:** ~4 sekundy

### 2. Lazy load Modbus CLI (oszczędność: ~0.35s)
- **Plik:** `boneio/bonecli.py`
- **Zmiana:** Modbus CLI importowany tylko dla komend modbus-*
- **Oszczędność:** ~0.35 sekundy

## 📊 Rezultat

**Przed:** ~15 sekund
**Po Etapie 1:** ~10.5 sekund
**Oszczędność:** ~4.35 sekundy (29%)

## 🎯 Dalsze optymalizacje (opcjonalne)

- Lazy load komponentów w config.loader (~2s)
- Lazy load OLED dependencies (~0.5s)
- Lazy load FastAPI routes (~1s)

**Potencjalna oszczędność:** dodatkowe ~3.5s


## DEBIAN 13

Pakiety do zainstalowania:

```bash
fonts-dejavu
python3.13-venv
```
```bash
sudo apt install fonts-dejavu python3.13-venv
```
```
sudo apt-get install -y \
    build-essential \
    python3-dev \
    python3-venv \
    libssl-dev \
    libffi-dev \
    libgpiod-dev \
    libjpeg-dev \
    zlib1g-dev \
    libfreetype6-dev \
    libopenjp2-7-dev \
    libtiff6 \
    libxcb1 \
    pkg-config
```

```
sudo apt remove bb-wlan0-defaults bb-wl18xx-firmware bluetooth bluez 
```

```
sudo timedatectl set-timezone Europe/Warsaw
sudo ufw allow from any to any port 8090
```