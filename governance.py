#!/usr/bin/env python3
"""Read-only provenance evidence for an installed Codex DMX Proxy payload.

This utility never changes provider configuration, Codex session state, or the
proxy listener. It reports only the proxy runtime and payload evidence already
available through the installed public control surface.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def _installed_control():
    """Load the control module adjacent to this shipped utility."""
    sys.modules.pop("control", None)
    spec = importlib.util.spec_from_file_location("control", HERE + "/control.py")
    if spec is None or spec.loader is None:
        raise RuntimeError("installed control.py is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules["control"] = module
    spec.loader.exec_module(module)
    return module


def collect() -> dict:
    """Return secret-free, read-only runtime provenance evidence."""
    control = _installed_control()
    return control.status(control._context())


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Read-only Codex DMX Proxy provenance evidence."
    )
    parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args()
    evidence = collect()
    if args.as_json:
        print(json.dumps(evidence, sort_keys=True))
        return
    integrity = evidence["payload_integrity"]
    print(f"release: {evidence['release'] or 'unavailable'}")
    print(f"payload integrity: {'ok' if integrity['ok'] else 'FAILED'} ({integrity['detail']})")
    runtime = evidence.get("runtime")
    if isinstance(runtime, dict):
        print(f"loaded source SHA-256: {runtime.get('source_sha256') or 'unavailable'}")
    else:
        print("loaded source SHA-256: unavailable")


if __name__ == "__main__":
    main()
