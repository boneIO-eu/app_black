"""Software interlock manager for output devices.

This module provides interlock functionality to prevent multiple outputs
in the same group from being active simultaneously.

Formerly located in: boneio.helper.interlock
"""

from boneio.const import ON


class SoftwareInterlockManager:
    def __init__(self):
        self.groups = {}  # group_name: set(relay_instances)

    def register(self, relay, group_names):
        for group in group_names:
            self.groups.setdefault(group, set()).add(relay)

    def can_turn_on(self, relay, group_names):
        for group in group_names:
            for other_relay in self.groups.get(group, []):
                if other_relay is not relay and getattr(other_relay, "state", None) == ON:
                    return False
        return True