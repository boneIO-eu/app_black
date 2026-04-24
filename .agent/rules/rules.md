---
trigger: always_on
---

# Coding Guidelines

- My project's programming language is python 3.13
- we want it to work with Home Assistant
- Use early returns when possible
- Always add documentation when creating new functions and classes
- Always write \_LOGGER messages in English
- I might contact you in Polish, then respond to me in Polish
- save all things you change in some MD files, so we can use it for documentation later
- we use i18n whenever possible
- create translations if you can or ask if you should create one
- always create reusable components and avoid creating new ones whenever possible, reusing existing components instead
- **System-level OS changes** (files in `/etc`, `/usr/sbin`, systemd units, sudoers, mosquitto config, etc.) MUST follow `.agent/rules/system-migrations.md`. Never edit `setup_boneio.sh` heredocs or existing released migrations — always add a new `boneio/migrations/versions/vX_Y_Z_*.py` module.
