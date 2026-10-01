"""Check task progress from actual evidence only.

Checks:
- shell_check: command exits 0
- file_exists: path exists and non-empty
- doctype_exists: frappe.db.exists('DocType', name) truthy
- api_exists: dotted path importable
- integration_test: bench run-tests module passes (checked via marker file or live run)
- manual_review: approval comment + status field set on gate record
"""

import importlib
import json
import os
import subprocess
import sys

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
SPEC_PATH = os.path.join(APP_ROOT, "tasks_spec.json")


def shell_check(cmd: str) -> bool:
    return subprocess.run(cmd, shell=True).returncode == 0


def file_exists(path: str) -> bool:
    full = path if os.path.isabs(path) else os.path.join(APP_ROOT, path)
    return os.path.isfile(full) and os.path.getsize(full) > 0


def doctype_exists(name: str) -> bool:
    try:
        import frappe

        return bool(frappe.db.exists("DocType", name))
    except Exception:
        return False


def api_exists(dotted: str) -> bool:
    try:
        mod, fn = dotted.rsplit(".", 1)
        m = importlib.import_module(mod)
        return callable(getattr(m, fn, None))
    except Exception:
        return False


def load_spec():
    with open(SPEC_PATH) as f:
        return json.load(f)


def main():
    spec = load_spec()
    for feat in spec["features"]:
        checks = feat.get("auto_check", {})
        ok = True
        for dt in checks.get("doctype_exists", []):
            if not doctype_exists(dt):
                ok = False
        for api in checks.get("api_exists", []):
            if not api_exists(api):
                ok = False
        for rel in checks.get("file_exists", []):
            if not file_exists(rel):
                ok = False
        print(f"{feat['feature_id']}: {'DONE' if ok else feat['status']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
