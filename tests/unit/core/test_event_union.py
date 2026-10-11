"""Every event model is in the ``Event`` union.

``WebSocketManager.broadcast_state`` drops anything that is not an instance
of it, so an event left out never reaches the panel, without an error.
"""

from pydantic import BaseModel

from boneio.models import events


def test_every_event_model_is_in_the_union():
    models = {
        cls for cls in vars(events).values()
        if isinstance(cls, type) and issubclass(cls, BaseModel) and "event_type" in cls.model_fields
    }
    assert models - set(events.Event.__args__) == set()
