# Event Architecture - Proposal

## Problem
Obecnie EventBus używa dict z mieszaniną danych:
```python
trigger_event({
    "event_type": "input",      # typ eventu
    "entity_id": "P8_41",       # ID encji
    "click_type": "single",     # kontekst zdarzenia
    "duration": 0.2,            # kontekst zdarzenia
    "event_state": InputState   # stan encji
})
```

**Problemy:**
- ❌ Brak type safety
- ❌ Łatwo o literówki
- ❌ Brak walidacji
- ❌ Trudne debugowanie
- ❌ Niejasna struktura

## Solution: Typed Event Classes

### Struktura
```python
from boneio.models.events import InputEvent, OutputEvent

# Input event - ma dodatkowy kontekst (click_type, duration)
event = InputEvent(
    entity_id="P8_41",
    click_type="single",
    duration=0.2,
    state=InputState(...)
)

# Output event - prosty, tylko zmiana stanu
event = OutputEvent(
    entity_id="OUT_05",
    state=OutputState(...)
)
```

### Użycie

#### 1. Triggerowanie eventu (Input)
```python
# W hardware/gpio/input/base.py
event = InputEvent(
    entity_id=self.id,
    click_type=click_type,
    duration=duration,
    state=InputState(
        name=self.name,
        state=self.last_state,
        type=self.input_type,
        pin=self.pin,
        timestamp=self.last_press_timestamp,
        boneio_input=self.boneio_input,
    )
)
self._event_bus.trigger_event(event)
```

#### 2. Triggerowanie eventu (Output)
```python
# W components/output/basic.py
event = OutputEvent(
    entity_id=self.id,
    state=OutputState(
        id=self.id,
        name=self.name,
        state=state,
        type=self.output_type,
        pin=self.pin_id,
        timestamp=self.last_timestamp,
        expander_id=self.expander_id,
    )
)
self._event_bus.trigger_event(event)
```

#### 3. Odbieranie eventu
```python
# EventBus - type-aware dispatch
async def _handle_event(self, event: Event):
    if isinstance(event, InputEvent):
        # Mamy type safety!
        entity_id = event.entity_id
        click_type = event.click_type  # IDE podpowiada
        state = event.state
    elif isinstance(event, OutputEvent):
        entity_id = event.entity_id
        state = event.state
```

#### 4. Listenery
```python
# Manager - otrzymuje konkretny typ
async def handle_input_event(self, event: InputEvent) -> None:
    input_instance = self._inputs.get(event.entity_id)
    actions = input_instance.get_actions_of_click(event.click_type)
    # ...

# WebUI - otrzymuje tylko State
async def output_state_changed(state: OutputState):
    await websocket_manager.broadcast_state("output", state)
```

## Korzyści

### 1. Type Safety
```python
# ✅ IDE podpowiada
event.click_type  # autocomplete działa
event.clck_type   # linter złapie błąd

# ❌ Dict
event["click_type"]  # brak autocomplete
event["clck_type"]   # runtime error
```

### 2. Separation of Concerns
```python
# State = stan encji (do zapisania w bazie, wyświetlenia w UI)
class InputState(BaseModel):
    name: str
    state: str
    pin: str

# Event = zdarzenie + kontekst (do przetworzenia)
class InputEvent(BaseModel):
    entity_id: str
    click_type: str    # kontekst zdarzenia
    duration: float    # kontekst zdarzenia
    state: InputState  # stan encji
```

### 3. Walidacja
```python
# Pydantic automatycznie waliduje
event = InputEvent(
    entity_id="P8_41",
    click_type="invalid",  # ❌ może dodać Enum validation
    duration="not a float"  # ❌ ValidationError
)
```

### 4. Dokumentacja
```python
class InputEvent(BaseModel):
    """Input event - triggered when input detects click/press.
    
    Attributes:
        entity_id: Unique input identifier
        click_type: Type of click (single, double, long, pressed, released)
        duration: Duration of the press in seconds
        state: Current state of the input
    """
    entity_id: str
    click_type: str
    duration: float | None
    state: InputState
```

## Migration Path

### Faza 1: Add Event Models (✅ Done)
- Stworzyć `models/events.py`
- Zdefiniować wszystkie typy eventów

### Faza 2: Update EventBus
- EventBus.trigger_event() przyjmuje Event
- EventBus._handle_event() dispatch po typie
- Backward compatibility z dict (deprecated)

### Faza 3: Update Producers
- Input → InputEvent
- Output → OutputEvent
- Sensor → SensorEvent
- Cover → CoverEvent

### Faza 4: Update Consumers
- Manager handlers używają typowanych eventów
- WebUI listeners używają State directly

### Faza 5: Remove Dict Support
- Usunąć deprecated dict support
- Clean up

## Podsumowanie

**Obecny stan (dict):**
- ✅ Elastyczność
- ❌ Brak type safety
- ❌ Brak walidacji
- ❌ Runtime errors

**Propozycja (Event classes):**
- ✅ Type safety
- ✅ Walidacja
- ✅ Separation of concerns
- ✅ IDE support
- ✅ Compile-time errors
- ✅ Elastyczność (różne Event classes)

**Rekomendacja:** Przejść na Event classes. Warto zainwestować czas teraz, żeby uniknąć problemów później.

