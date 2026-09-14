"""``boneio accounts`` — manage web UI accounts from the shell.

This is the recovery path. A device whose administrator password is lost has no
other way back in: there is no email to send a link to, and wiping
``users.json`` by hand would take every other account with it.

It is also how a controller gets an account without a browser, which makes
provisioning scriptable and means a freshly flashed device does not have to be
clicked through the wizard.

Passwords are never taken from the command line. An argument is visible in
``ps`` to every user on the box and lands in shell history, so they are always
prompted for, with echo off.

Changes take effect immediately: the running web server notices that
``users.json`` changed and re-reads it, so recovering a password does not mean
restarting a controller in the middle of whatever it is automating.
"""

from __future__ import annotations

import argparse
import getpass
import logging
import os
import sys
from pathlib import Path

from boneio.core.auth.models import Role
from boneio.core.auth.store import UserStore, UserStoreError, validate_password

_LOGGER = logging.getLogger(__name__)


def _prompt_password(prompt: str) -> str | None:
    """Ask for a password twice, with echo off.

    Args:
        prompt: Text for the first prompt.

    Returns:
        The password, or None if the two entries differed, it was empty, or the
        policy rejected it.
    """
    first = getpass.getpass(f"{prompt}: ")
    if not first:
        print("Aborted: empty password.", file=sys.stderr)
        return None

    try:
        validate_password(first)
    except UserStoreError as err:
        print(f"Rejected: {err}", file=sys.stderr)
        return None

    second = getpass.getpass("Repeat password: ")
    if first != second:
        print("Aborted: the passwords do not match.", file=sys.stderr)
        return None

    return first


def _warn_on_ownership(store: UserStore, config_path: Path) -> None:
    """Warn when the file was written as the wrong user.

    Running this under ``sudo`` leaves ``users.json`` owned by root, and the
    service — which runs as the ``boneio`` user — then cannot rewrite it. The
    failure would only show up later, when someone changes a password from the
    web UI and it silently fails, so it is called out here instead.

    Args:
        store: The account store just written.
        config_path: Path to config.yaml, used as the reference owner.
    """
    try:
        written_uid = store.path.stat().st_uid
        expected_uid = config_path.stat().st_uid
    except OSError:
        return

    if written_uid != expected_uid:
        print(
            f"WARNING: {store.path} is now owned by uid {written_uid}, but "
            f"{config_path} belongs to uid {expected_uid}. The boneIO service "
            f"probably cannot write it. Fix with:\n"
            f"  sudo chown {expected_uid} {store.path}",
            file=sys.stderr,
        )


def run_accounts_command(args: argparse.Namespace) -> int:
    """Execute an ``accounts`` subcommand.

    Args:
        args: Parsed arguments, carrying ``accounts_action``, ``config`` and,
            depending on the subcommand, ``username`` and ``role``.

    Returns:
        Process exit code.
    """
    config_path = Path(args.config).expanduser()
    if not config_path.exists():
        print(f"No config file at {config_path}", file=sys.stderr)
        return 1

    store = UserStore.for_config_file(config_path)
    try:
        store.load()
    except UserStoreError as err:
        print(f"Cannot read the account store: {err}", file=sys.stderr)
        return 1

    action = args.accounts_action

    if action == "list":
        users = store.list_users()
        if not users:
            print(f"No accounts yet ({store.path} does not exist).")
            print("Create one with:  boneio accounts add <username> --role admin")
            return 0
        width = max(len(user.username) for user in users)
        for user in users:
            print(f"{user.username:<{width}}  {user.role}  created {user.created_at}")
        return 0

    if action == "add":
        password = _prompt_password(f"New password for '{args.username}'")
        if password is None:
            return 1
        try:
            user = store.add_user(args.username, password, Role(args.role))
        except UserStoreError as err:
            print(f"Could not create the account: {err}", file=sys.stderr)
            return 1
        _warn_on_ownership(store, config_path)
        print(f"Created {user.role} account '{user.username}'.")
        return 0

    if action == "reset":
        if store.get_user(args.username) is None:
            print(f"No such account: {args.username}", file=sys.stderr)
            return 1
        password = _prompt_password(f"New password for '{args.username}'")
        if password is None:
            return 1
        try:
            store.set_password(args.username, password)
        except UserStoreError as err:
            print(f"Could not change the password: {err}", file=sys.stderr)
            return 1
        _warn_on_ownership(store, config_path)
        print(f"Password changed for '{args.username}'. It takes effect immediately.")
        return 0

    if action == "delete":
        try:
            store.delete_user(args.username)
        except UserStoreError as err:
            print(f"Could not delete the account: {err}", file=sys.stderr)
            return 1
        print(f"Deleted account '{args.username}'.")
        return 0

    print(f"Unknown accounts action: {action}", file=sys.stderr)
    return 1


def add_accounts_parser(subparsers: argparse._SubParsersAction) -> None:
    """Register the ``accounts`` subcommand.

    Args:
        subparsers: The top-level subparser collection from bonecli.
    """
    accounts_parser = subparsers.add_parser(
        "accounts",
        help="Manage web UI accounts (create, reset a password, list, delete)",
        description=(
            "Manage the accounts in users.json. This is the recovery path when "
            "an administrator password is lost, and the way to provision a "
            "device without a browser. Passwords are always prompted for, "
            "never passed as arguments."
        ),
    )
    # bonecli's main() reads args.debug before dispatching, so every subcommand
    # has to carry one.
    accounts_parser.set_defaults(debug=0)
    accounts_parser.add_argument(
        "-c",
        "--config",
        metavar="path_to_config",
        default=os.environ.get("BONEIO_CONFIG", "./config.yaml"),
        help="boneIO config file; users.json lives next to it",
    )

    actions = accounts_parser.add_subparsers(dest="accounts_action", required=True)

    actions.add_parser("list", help="List accounts and their roles")

    add_action = actions.add_parser("add", help="Create an account")
    add_action.add_argument("username", help="Username to create")
    add_action.add_argument(
        "--role",
        choices=[str(Role.ADMIN), str(Role.VIEWER)],
        default=str(Role.VIEWER),
        help="Role to grant (default: viewer)",
    )

    reset_action = actions.add_parser("reset", help="Set a new password")
    reset_action.add_argument("username", help="Account to change")

    delete_action = actions.add_parser("delete", help="Remove an account")
    delete_action.add_argument("username", help="Account to remove")
