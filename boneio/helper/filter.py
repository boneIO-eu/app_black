"""Filter class to adjust sensor values."""
from __future__ import annotations


FILTERS = {
    "offset": lambda x, y: x + y,
    "round": lambda x, y: round(x, y),
    "multiply": lambda x, y: x * y,
    "filter_out": lambda x, y: None if x == y else x,
    "filter_out_greater": lambda x, y: None if x > y else x,
    "filter_out_lower": lambda x, y: None if x < y else x,
}


class Filter:
    _filters = []

    def _apply_filters(self, value: float) -> float | None:
        for filter in self._filters:
            for k, v in filter.items():
                if k not in FILTERS:
                    break
                value = FILTERS[k](value, v)
                if value is None:
                    return None
        return value
