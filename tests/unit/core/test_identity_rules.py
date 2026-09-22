"""Tests for the rules that turn a typed name into an entity's identifier.

The identifier reaches an MQTT topic, Home Assistant's unique_id, the state
file and every reference a condition or an action writes. So the rules worth
pinning are: a name is enough, an explicit id still wins, and two names that
fold to the same identifier are refused *at load time* rather than producing
one entity with the second silently dropped at startup.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from boneio.core.config.yaml_util import load_config_from_file
from boneio.exceptions import ConfigurationException

HEAD = "boneio:\n  name: T\n"

TRIGGER = "    trigger:\n      type: time\n      at: \"20:00\"\n"
ACTIONS = "    actions:\n      - action: mqtt\n        topic: t/x\n"


def load(body: str) -> dict:
    """Load a config from a string, the way the device loads config.yaml."""
    directory = tempfile.mkdtemp()
    path = os.path.join(directory, "config.yaml")
    with open(path, "w") as handle:
        handle.write(HEAD + body)
    return load_config_from_file(config_file=path)


class TestAVirtualSwitchNeedsOnlyAName:
    def test_a_name_is_accepted_on_its_own(self):
        config = load("virtual_switch:\n  - name: Nie ma nas w domu\n")
        assert config["virtual_switch"][0]["name"] == "Nie ma nas w domu"

    def test_a_description_is_carried_and_read_by_nothing(self):
        config = load(
            "virtual_switch:\n  - name: Away\n    description: Flaga symulacji\n"
        )
        assert config["virtual_switch"][0]["description"] == "Flaga symulacji"

    def test_a_switch_with_no_name_is_refused(self):
        with pytest.raises(ConfigurationException) as excinfo:
            load("virtual_switch:\n  - description: no name here\n")
        assert "name" in str(excinfo.value)

    def test_an_explicit_id_is_still_accepted(self):
        """It exists so the reference survives a rename."""
        config = load("virtual_switch:\n  - id: away\n    name: Nie ma nas w domu\n")
        assert config["virtual_switch"][0]["id"] == "away"


class TestIdentifiersHaveToBeDistinct:
    """Names do not have to be unique. What they are turned into does."""

    def test_two_names_that_fold_together_are_refused(self):
        with pytest.raises(ConfigurationException) as excinfo:
            load("virtual_switch:\n  - name: Salon\n  - name: 'salon!'\n")
        message = str(excinfo.value)
        assert "salon" in message
        assert "explicit 'id'" in message, message

    def test_an_explicit_id_resolves_the_clash(self):
        config = load(
            "virtual_switch:\n  - name: Salon\n  - name: 'salon!'\n    id: salon_2\n"
        )
        assert len(config["virtual_switch"]) == 2

    def test_a_name_with_nothing_usable_in_it_is_refused(self):
        """"!!!" folds to the empty string, which is not an identifier."""
        with pytest.raises(ConfigurationException) as excinfo:
            load("virtual_switch:\n  - name: '!!!'\n")
        assert "identifier" in str(excinfo.value)

    def test_accents_do_not_make_two_switches_collide(self):
        """Folding is aggressive enough to be worth checking in the other
        direction: these two must stay distinct."""
        config = load("virtual_switch:\n  - name: Łazienka\n  - name: Kuchnia\n")
        assert len(config["virtual_switch"]) == 2

    def test_the_rule_applies_to_schedules_too(self):
        with pytest.raises(ConfigurationException) as excinfo:
            load(
                "schedule:\n"
                "  - name: Wieczór\n" + TRIGGER + ACTIONS +
                "  - name: 'wieczor'\n" + TRIGGER + ACTIONS
            )
        assert "wieczor" in str(excinfo.value)


class TestSelfReferenceThroughADerivedId:
    """The runtime guard stops the recursion by refusing to act, so the config
    would load, look right and do half of what it says."""

    def test_a_switch_whose_action_sets_itself_is_refused(self):
        with pytest.raises(ConfigurationException) as excinfo:
            load(
                "virtual_switch:\n"
                "  - name: Away\n"
                "    actions:\n"
                "      on_turn_on:\n"
                "        - action: virtual_switch\n"
                "          boneio_virtual_switch: away\n"
                '          action_output: "OFF"\n'
            )
        assert "sets itself" in str(excinfo.value)

    def test_setting_a_different_switch_is_fine(self):
        config = load(
            "virtual_switch:\n"
            "  - name: Away\n"
            "    actions:\n"
            "      on_turn_on:\n"
            "        - action: virtual_switch\n"
            "          boneio_virtual_switch: guest_mode\n"
            '          action_output: "OFF"\n'
            "  - name: Guest mode\n"
        )
        assert len(config["virtual_switch"]) == 2


class TestDanglingVirtualSwitchReferences:
    """A reference to a virtual switch the config never defines is refused.

    Which way the runtime fails is the reason this is worth catching here: an
    unresolvable condition entity is logged and the action **runs anyway**. For
    "only while nobody is home" that is backwards — one wrong letter and every
    step of a presence simulation fires while somebody is in the house, with
    no flag able to stop it and a single warning in the log to say why.
    """

    SWITCH = "virtual_switch:\n  - name: Presence away\n"

    def test_a_typo_in_a_schedule_condition_is_refused(self):
        with pytest.raises(ConfigurationException) as excinfo:
            load(
                self.SWITCH
                + "schedule:\n"
                "  - name: Wieczor\n"
                "    condition:\n"
                "      type: state\n"
                "      entity: virtual_switch\n"
                "      entity_id: presence_awya\n" + TRIGGER + ACTIONS
            )
        message = str(excinfo.value)
        assert "presence_awya" in message
        # The message names what *is* defined, because the answer is usually
        # one letter away from the question.
        assert "presence_away" in message

    def test_the_right_reference_is_accepted(self):
        config = load(
            self.SWITCH
            + "schedule:\n"
            "  - name: Wieczor\n"
            "    condition:\n"
            "      type: state\n"
            "      entity: virtual_switch\n"
            "      entity_id: presence_away\n" + TRIGGER + ACTIONS
        )
        assert len(config["schedule"]) == 1

    def test_a_typo_in_an_action_target_is_refused(self):
        with pytest.raises(ConfigurationException) as excinfo:
            load(
                self.SWITCH
                + "event:\n"
                "  - boneio_input: in_11\n"
                "    actions:\n"
                "      single:\n"
                "        - action: virtual_switch\n"
                "          boneio_virtual_switch: guest_mode\n"
                '          action_output: "ON"\n'
            )
        message = str(excinfo.value)
        assert "guest_mode" in message
        # Inputs have no id, so the pin is what identifies them to somebody
        # hunting the typo.
        assert "in_11" in message, message

    def test_a_typo_in_a_condition_on_an_action_is_refused(self):
        with pytest.raises(ConfigurationException) as excinfo:
            load(
                self.SWITCH
                + "event:\n"
                "  - boneio_input: in_11\n"
                "    actions:\n"
                "      single:\n"
                "        - action: mqtt\n"
                "          topic: t/x\n"
                "          condition:\n"
                "            type: state\n"
                "            entity: virtual_switch\n"
                "            entity_id: nope\n"
            )
        assert "nope" in str(excinfo.value)

    def test_a_grouped_condition_list_is_walked_too(self):
        with pytest.raises(ConfigurationException) as excinfo:
            load(
                self.SWITCH
                + "schedule:\n"
                "  - name: Wieczor\n"
                "    conditions:\n"
                "      mode: and\n"
                "      list:\n"
                "        - type: sun\n"
                "          after: civil_dusk\n"
                "        - type: state\n"
                "          entity: virtual_switch\n"
                "          entity_id: missing_one\n" + TRIGGER + ACTIONS
            )
        assert "missing_one" in str(excinfo.value)

    def test_one_switch_referring_to_another_is_checked(self):
        with pytest.raises(ConfigurationException) as excinfo:
            load(
                "virtual_switch:\n"
                "  - name: Away\n"
                "    actions:\n"
                "      on_turn_on:\n"
                "        - action: virtual_switch\n"
                "          boneio_virtual_switch: guest_mode\n"
                '          action_output: "OFF"\n'
            )
        assert "guest_mode" in str(excinfo.value)

    def test_conditions_on_other_entity_types_are_left_alone(self):
        """Outputs, covers and inputs come from several places — a board file,
        an expander, a remote device — so the same check on them would reject
        configurations that work. Only virtual switches have exactly one
        source, which is what makes this safe."""
        config = load(
            self.SWITCH
            + "schedule:\n"
            "  - name: Wieczor\n"
            "    condition:\n"
            "      type: state\n"
            "      entity: output\n"
            "      entity_id: out_that_is_defined_by_the_board\n" + TRIGGER + ACTIONS
        )
        assert len(config["schedule"]) == 1
