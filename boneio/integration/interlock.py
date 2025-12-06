"""Software interlock manager for output devices.

This module provides interlock functionality to prevent multiple outputs
in the same group from being active simultaneously.

Formerly located in: boneio.helper.interlock
"""

from boneio.const import ON


class SoftwareInterlockManager:
    """Manager for software interlocks between outputs.
    
    Prevents multiple outputs in the same group from being active simultaneously.
    """
    
    def __init__(self):
        self.groups: dict[str, set] = {}  # group_name: set(relay_instances)

    def register(self, relay, group_names: list[str]) -> None:
        """Register a relay to one or more interlock groups.
        
        Args:
            relay: The relay instance to register
            group_names: List of group names to register the relay to
        """
        for group in group_names:
            self.groups.setdefault(group, set()).add(relay)

    def can_turn_on(self, relay, group_names: list[str]) -> bool:
        """Check if a relay can be turned on without violating interlocks.
        
        Args:
            relay: The relay instance to check
            group_names: List of group names the relay belongs to
            
        Returns:
            True if the relay can be turned on, False if another relay in the group is ON
        """
        for group in group_names:
            for other_relay in self.groups.get(group, []):
                if other_relay is not relay and getattr(other_relay, "state", None) == ON:
                    return False
        return True

    def get_all_groups(self) -> list[str]:
        """Get list of all registered interlock group names.
        
        Returns:
            Sorted list of unique group names
        """
        return sorted(self.groups.keys())

    def clear(self) -> None:
        """Clear all registered relays from all groups.
        
        Used during configuration reload to remove stale references.
        """
        self.groups.clear()