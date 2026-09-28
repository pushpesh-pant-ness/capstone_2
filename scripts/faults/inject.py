#!/usr/bin/env python
"""CLI for triggering/clearing faults defined in registry.yaml.

Usage:
    python inject.py list
    python inject.py trigger <fault-id>
    python inject.py clear <fault-id>
    python inject.py clear-all
    python inject.py status
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).parent))
import _handlers as h  # noqa: E402

REGISTRY_PATH = Path(__file__).parent / "registry.yaml"


def load_registry() -> list[dict]:
    with open(REGISTRY_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)["faults"]


def find_fault(fault_id: str) -> dict:
    for fault in load_registry():
        if fault["id"] == fault_id:
            return fault
    raise SystemExit(f"Unknown fault id '{fault_id}'. Run 'list' to see available faults.")


def apply_fault(fault: dict, on: bool) -> None:
    if fault["type"] == "flagd":
        variant = fault["on_variant"] if on else fault["off_variant"]
        h.set_flagd_variant(fault["flag_key"], variant)
    elif fault["type"] == "crash_loop":
        h.set_crash_liveness_probe(fault["target_deployment"], enable=on)
    else:
        raise SystemExit(f"Unknown fault type '{fault['type']}'")


def cmd_list(_args: argparse.Namespace) -> None:
    for fault in load_registry():
        print(f"{fault['id']:<24} [{fault['severity']:<8}] {fault['expected_root_cause']}")


def cmd_trigger(args: argparse.Namespace) -> None:
    fault = find_fault(args.fault_id)
    apply_fault(fault, on=True)
    print(f"Triggered '{fault['id']}' — expect alert '{fault['expected_alert']}' within a few minutes.")


def cmd_clear(args: argparse.Namespace) -> None:
    fault = find_fault(args.fault_id)
    apply_fault(fault, on=False)
    print(f"Cleared '{fault['id']}'.")


def cmd_clear_all(_args: argparse.Namespace) -> None:
    for fault in load_registry():
        apply_fault(fault, on=False)
        print(f"Cleared '{fault['id']}'.")


def cmd_status(_args: argparse.Namespace) -> None:
    for fault in load_registry():
        if fault["type"] == "flagd":
            current = h.get_flagd_variant(fault["flag_key"])
            active = current != fault["off_variant"]
        else:
            active = "unknown (crash_loop faults aren't queryable; assume cleared after 'clear')"
        print(f"{fault['id']:<24} active={active}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list").set_defaults(func=cmd_list)
    sub.add_parser("status").set_defaults(func=cmd_status)
    sub.add_parser("clear-all").set_defaults(func=cmd_clear_all)

    trigger_parser = sub.add_parser("trigger")
    trigger_parser.add_argument("fault_id")
    trigger_parser.set_defaults(func=cmd_trigger)

    clear_parser = sub.add_parser("clear")
    clear_parser.add_argument("fault_id")
    clear_parser.set_defaults(func=cmd_clear)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
