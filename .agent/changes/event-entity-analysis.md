# Analiza: Czy Event Entity może wysyłać eventy na starcie?

## Wynik: NIE znaleziono buga z event entity

### Przeanalizowane ścieżki

#### 1. Boot press suppression ✅ BEZPIECZNE
- `_seed_initial_states()` w GPIO manager armuje `_boot_press_suppressed=True`
  na `MultiClickDetector` (event entity) gdy pin jest LOW na starcie
- Pierwsza phantom FALLING_EDGE jest ignorowana (linia 498-508 detectors.py)
- Timing jest bezpieczny: `_seed_initial_states` (sync) uruchamia się PRZED 
  jakimkolwiek edge callbackiem z event loop

#### 2. MQTT event publish ✅ BEZPIECZNE
- Event entity publish jest bez `retain=True` (domyślnie `retain=False`)
- Broker MQTT nie retainuje tych wiadomości
- Na restarcie/reconnect HA nie otrzymuje starych eventów

#### 3. _broadcast_all_input_states ✅ BEZPIECZNE
- `click_type=None` → blokowane na linii 778 handle_input_event

#### 4. _resend_all_states (MQTT reconnect) ✅ BEZPIECZNE
- Wysyła tylko outputs i covers, nie event entities

#### 5. EventBus ✅ BEZPIECZNE
- Prosta async queue, brak replay/buffer

### Co kolega mógł zobaczyć?

Prawdopodobnie widział **binary sensor** `pressed`/`released` wiadomości MQTT
(z `publish_only=True` eventów), nie event entity `{"event_type": "single"}`.

Oba typy inputów publikują na ten sam topic pattern: `{prefix}/input/{id}`
- Event entity: `{"event_type": "single"}` (JSON)
- Binary sensor: `"pressed"` / `"released"` (plain string)

Binary sensor z `initial_send=True` wysyła `pressed`/`released` do MQTT na starcie
→ kolega mógł to zobaczyć w logach MQTT i pomylić z event entity.

### Potencjalny problem (nie bug, ale ryzyko):
`BinarySensorDetector` NIE ma `_boot_press_suppressed` (w odróżnieniu od 
`MultiClickDetector`). Ale to jest OK bo:
- Binary sensor reaguje na zmianę stanu (edge), nie na "click"
- `current_state` jest inicjalizowane jako `False` (released)
- Jeśli pin jest LOW na starcie → FALLING_EDGE → `is_pressed=True` vs `current_state=False`
  → callback → wyśle "pressed" do MQTT
- To jest zamierzone zachowanie (informuje HA o bieżącym stanie kontaktu)
