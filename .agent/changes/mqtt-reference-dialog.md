# MQTT Reference Dialog

## Opis
Nowa funkcja "MQTT Reference" — wyświetla tematy i payloady MQTT dla dowolnej encji (wyjście, roleta, wejście, grupa, zdalne wyjście). Dostępne z dialogu long press na stronach Outputs i Inputs.

## Cel
Ułatwienie integracji z Node-RED — użytkownik kopiuje Topic i Payload bezpośrednio z interfejsu.

## Architektura

### Backend API
- Endpoint: `GET /api/mqtt_reference/{entity_type}/{entity_id}`
- Odpowiedź: JSON z `publish[]` (komendy) i `subscribe[]` (stan)
- Typy encji: `output`, `output_group`, `cover`, `input`, `remote_outputs`
- **MCP-ready**: ta sama odpowiedź JSON może być zwrócona przez przyszły MCP tool

### Frontend
- Komponent: `MqttReferenceSheet.tsx` — dialog z listą topików i payloadów
- Każde pole ma przycisk kopiowania (Topic oddzielnie, Payload oddzielnie)
- Sekcje: 📤 Publish (komendy) i 📥 Subscribe (stan)
- Wejścia wyświetlają komunikat "read-only" gdy brak komend

### Zmiany w UI
- **OutputsView**: Refactoring long press z prostego "confirm" na multi-option dialog (📡 MQTT Reference + ⚙️ Ustawienia)
- **InputsView**: Dodanie przycisku 📡 MQTT Reference (między Quick Action a Settings)

## Pliki
- `boneio/webui/routes/mqtt_reference.py` — nowy route
- `boneio/webui/routes/__init__.py` — rejestracja
- `boneio/webui/app.py` — include_router + DI override
- `frontend/src/components/MqttReferenceSheet.tsx` — komponent UI
- `frontend/src/components/OutputsView.tsx` — refactoring dialogu
- `frontend/src/components/InputsView.tsx` — dodanie MQTT ref
- `frontend/src/locales/en/common.json` — tłumaczenia EN
- `frontend/src/locales/pl/common.json` — tłumaczenia PL

## Formaty MQTT

### Output (switch)
```
Publish:
  {prefix}/cmd/output/{id}/set → ON / OFF / TOGGLE
Subscribe:
  {prefix}/output/{id} → {"state": "ON"} / {"state": "OFF"}
```

### Output (light)
```
+ {prefix}/cmd/output/{id}/set_brightness → 0-255
```

### Cover
```
Publish:
  {prefix}/cmd/cover/{id}/set → OPEN / CLOSE / STOP / TOGGLE
  {prefix}/cmd/cover/{id}/pos → 0-100
  {prefix}/cmd/cover/{id}/tilt → 0-100 (venetian only)
Subscribe:
  {prefix}/cover/{id}/state → open / closed / opening / closing
  {prefix}/cover/{id}/pos → {"position": 0-100}
```

### Input (read-only)
```
Subscribe:
  {prefix}/input/{id} → {"state": "PRESSED"} / {"state": "RELEASED"}
```

### Group
```
Publish:
  {prefix}/cmd/group/{id}/set → ON / OFF / TOGGLE
Subscribe:
  {prefix}/group/{id} → {"state": "ON"} / {"state": "OFF"}
```
