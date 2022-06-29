from typing import Any, Callable, TypeVar

CALLABLE_T = TypeVar("CALLABLE_T", bound=Callable[..., Any])
CALLBACK_TYPE = Callable[[], None]


def callback(func: CALLABLE_T) -> CALLABLE_T:
    """Annotation to mark method as safe to call from within the event loop."""
    setattr(func, "_boneio_callback", True)
    return func


def is_callback(func: Callable[..., Any]) -> bool:
    """Check if function is safe to be called in the event loop."""
    return getattr(func, "_boneio_callback", False) is True
