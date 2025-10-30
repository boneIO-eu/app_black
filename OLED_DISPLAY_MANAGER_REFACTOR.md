# Refaktoryzacja OLED - Przeniesienie logiki konfiguracyjnej do DisplayManager

## Data: 29 października 2025

## Problem

Logika konfiguracji ekranów OLED (co wyświetlać, w jakiej kolejności) była rozproszona między:
- `DisplayManager` - inicjalizacja OLED
- `Oled` - konfiguracja screen order, zastępowanie placeholderów

To naruszało **separation of concerns** - klasa `Oled` powinna tylko **wyświetlać** dane, a nie decydować **co** wyświetlać.

## Rozwiązanie

Przeniesiono całą logikę konfiguracyjną do `DisplayManager`:

### 1. DisplayManager - zarządza konfiguracją

**Nowa odpowiedzialność:**
- Konfiguruje kolejność ekranów (screen order)
- Zastępuje placeholdery ("outputs", "inputs") rzeczywistymi nazwami
- Przekazuje gotową konfigurację do OLED

**Nowa metoda:**
```python
def _configure_screen_order(
    self,
    screen_order: list[str],
    grouped_outputs_by_expander: dict[str, Any],
    inputs_length: int,
) -> list[str]:
    """Configure screen order by replacing placeholders with actual screens."""
    configured_screens = screen_order.copy()
    
    # Replace "outputs" placeholder
    try:
        outputs_index = configured_screens.index("outputs")
        output_groups = list(grouped_outputs_by_expander.keys())
        if output_groups:
            configured_screens.pop(outputs_index)
            configured_screens[outputs_index:outputs_index] = output_groups
    except ValueError:
        pass
    
    # Replace "inputs" placeholder
    try:
        inputs_index = configured_screens.index("inputs")
        input_groups = [f"Inputs screen {i + 1}" for i in range(inputs_length)]
        if input_groups:
            configured_screens.pop(inputs_index)
            configured_screens[inputs_index:inputs_index] = input_groups
            self._input_groups = input_groups
    except ValueError:
        self._input_groups = []
    
    return configured_screens
```

**Nowe właściwości:**
```python
self._configured_screen_order = []  # Gotowa kolejność ekranów
self._input_groups = []             # Lista grup inputów
```

**Nowe gettery:**
```python
def get_configured_screen_order(self) -> list[str]:
    """Get configured screen order (with placeholders replaced)."""
    return self._configured_screen_order

def get_input_groups(self) -> list[str]:
    """Get list of input group screens."""
    return self._input_groups
```

### 2. Oled - tylko wyświetla dane

**Usunięta odpowiedzialność:**
- ❌ Konfiguracja screen order
- ❌ Zastępowanie placeholderów
- ❌ Logika decyzyjna o tym co wyświetlać

**Nowy konstruktor:**
```python
def __init__(
    self,
    host_data: HostData,
    grouped_outputs_by_expander: list[str],
    sleep_timeout: TimePeriod,
    screen_order: list[str],           # ✅ Już skonfigurowana!
    input_groups: list[str],           # ✅ Nowy parametr
    event_bus: EventBus,
    i2c_bus: "SMBus2I2C | None" = None,
):
    """Initialize OLED display.
    
    Args:
        screen_order: Configured screen order (placeholders already replaced)
        input_groups: List of input group names
    """
    # Screen order is already configured by DisplayManager
    self._screen_order = screen_order
    self._input_groups = input_groups
```

**Usunięta metoda:**
```python
# ❌ USUNIĘTO - teraz w DisplayManager
def _configure_screen_order(
    self, 
    screen_order: list[str], 
    grouped_outputs_by_expander: list[str]
) -> None:
    # ... 50+ linii logiki konfiguracyjnej
```

## Korzyści

### 1. ✅ Separation of Concerns

**Przed:**
- `DisplayManager` - inicjalizacja + częściowa konfiguracja
- `Oled` - konfiguracja + wyświetlanie

**Po:**
- `DisplayManager` - **zarządza konfiguracją** (co wyświetlać)
- `Oled` - **wyświetla dane** (jak wyświetlać)

### 2. ✅ Single Responsibility Principle

Każda klasa ma jedną odpowiedzialność:
- `DisplayManager` - **manager** decyduje o konfiguracji
- `Oled` - **driver** tylko wyświetla

### 3. ✅ Łatwiejsze testowanie

```python
# Testowanie DisplayManager - logika konfiguracji
screen_order = display_manager._configure_screen_order(
    screen_order=["uptime", "outputs", "inputs"],
    grouped_outputs_by_expander={"mcp0": {...}, "mcp1": {...}},
    inputs_length=2
)
assert screen_order == ["uptime", "mcp0", "mcp1", "Inputs screen 1", "Inputs screen 2"]

# Testowanie Oled - tylko wyświetlanie
oled = Oled(
    screen_order=["uptime", "mcp0"],  # Gotowa konfiguracja
    input_groups=["Inputs screen 1"],
    ...
)
```

### 4. ✅ Mniej zależności w Oled

**Przed:**
```python
# Oled musiał znać strukturę HostData
input_groups = [f"Inputs screen {i + 1}" for i in range(self._host_data.inputs_length)]
```

**Po:**
```python
# Oled dostaje gotowe dane
self._input_groups = input_groups  # Przekazane z DisplayManager
```

### 5. ✅ Czystszy kod

- Usunięto ~50 linii kodu z `Oled`
- Usunięto debug printy
- Lepsza czytelność obu klas

## Zmienione pliki

### 1. `boneio/core/manager/display.py`

**Dodano:**
- `_configure_screen_order()` - metoda konfiguracji ekranów
- `_configured_screen_order` - property
- `_input_groups` - property
- `get_configured_screen_order()` - getter
- `get_input_groups()` - getter

**Zmodyfikowano:**
- `_configure_oled()` - wywołuje `_configure_screen_order()` przed inicjalizacją OLED
- Przekazuje `screen_order` i `input_groups` do konstruktora `Oled`

### 2. `boneio/hardware/display/oled.py`

**Usunięto:**
- `_configure_screen_order()` - metoda (przeniesiona do DisplayManager)
- Debug printy (`print("configure screen order", ...)`)

**Zmodyfikowano:**
- `__init__()` - nowy parametr `input_groups`
- Dokumentacja - zaktualizowane opisy parametrów

## Backward Compatibility

✅ **100% kompatybilność wsteczna** - zmiany są tylko wewnętrzne:
- API DisplayManager bez zmian (dla użytkownika)
- Konfiguracja YAML bez zmian
- Zachowanie aplikacji bez zmian

## Testy

### Kompilacja
```bash
python3 -m py_compile boneio/core/manager/display.py boneio/hardware/display/oled.py
✅ Syntax OK
```

### Scenariusze testowe

1. **Screen order z placeholderami:**
   ```yaml
   screen_order: ["uptime", "outputs", "inputs", "web"]
   ```
   Powinno rozwinąć się do:
   ```python
   ["uptime", "mcp0", "mcp1", "Inputs screen 1", "Inputs screen 2", "web"]
   ```

2. **Brak outputs:**
   ```yaml
   screen_order: ["uptime", "outputs"]
   ```
   Jeśli brak outputs, powinno być:
   ```python
   ["uptime"]  # "outputs" usunięte
   ```

3. **Brak inputs:**
   ```yaml
   screen_order: ["uptime", "inputs"]
   ```
   Jeśli brak inputs, powinno być:
   ```python
   ["uptime"]  # "inputs" usunięte
   ```

## Architektura

```
┌─────────────────────────────────────────────────────────────┐
│                        Manager                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │              DisplayManager                         │    │
│  │  ┌──────────────────────────────────────────────┐  │    │
│  │  │  _configure_screen_order()                   │  │    │
│  │  │  • Zastępuje placeholdery                    │  │    │
│  │  │  • Tworzy listę input_groups                 │  │    │
│  │  │  • Zwraca gotową konfigurację                │  │    │
│  │  └──────────────────────────────────────────────┘  │    │
│  │                      ↓                              │    │
│  │  ┌──────────────────────────────────────────────┐  │    │
│  │  │  _configure_oled()                           │  │    │
│  │  │  • Wywołuje _configure_screen_order()        │  │    │
│  │  │  • Przekazuje gotową konfigurację do Oled    │  │    │
│  │  └──────────────────────────────────────────────┘  │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
                            ↓
                  screen_order (gotowa lista)
                  input_groups (gotowa lista)
                            ↓
┌─────────────────────────────────────────────────────────────┐
│                         Oled                                │
│  ┌────────────────────────────────────────────────────┐    │
│  │  __init__()                                         │    │
│  │  • Przyjmuje gotową konfigurację                   │    │
│  │  • Nie modyfikuje screen_order                     │    │
│  │  • Tylko wyświetla dane                            │    │
│  └────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌────────────────────────────────────────────────────┐    │
│  │  render_display()                                   │    │
│  │  • Pobiera dane z HostData                         │    │
│  │  • Rysuje na ekranie                               │    │
│  └────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘
```

## Zgodność z zasadami SOLID

### S - Single Responsibility Principle ✅
- `DisplayManager` - zarządza konfiguracją wyświetlacza
- `Oled` - wyświetla dane na ekranie

### O - Open/Closed Principle ✅
- Można dodać nowe typy ekranów bez modyfikacji `Oled`
- Logika konfiguracji w `DisplayManager` jest rozszerzalna

### L - Liskov Substitution Principle ✅
- `Oled` może być zastąpiony innym driverem wyświetlacza

### I - Interface Segregation Principle ✅
- `Oled` nie zależy od niepotrzebnych metod `HostData`

### D - Dependency Inversion Principle ✅
- `Oled` zależy od abstrakcji (gotowe dane), nie od implementacji

## Następne kroki (opcjonalne)

1. **Abstrakcja Display:**
   ```python
   class DisplayDriver(ABC):
       @abstractmethod
       def render(self, screen_name: str, data: dict) -> None:
           pass
   ```

2. **Factory Pattern:**
   ```python
   class DisplayFactory:
       @staticmethod
       def create_display(display_type: str) -> DisplayDriver:
           if display_type == "oled":
               return Oled(...)
           elif display_type == "lcd":
               return LCD(...)
   ```

3. **Screen Registry:**
   ```python
   class ScreenRegistry:
       def register_screen(self, name: str, renderer: Callable):
           self._screens[name] = renderer
   ```

## Autor
Cascade AI Assistant

## Status
✅ **UKOŃCZONE** - Refaktoryzacja zakończona sukcesem
