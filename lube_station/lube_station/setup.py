"""Idempotent setup: print formats and other seeded records."""

import json

import frappe


PRINT_FORMATS = [
    ("lube_station", "print_format", "hosting_invoice", "hosting_invoice.json"),
]

_PRINT_FIELDS = [
    "name",
    "doc_type",
    "module",
    "standard",
    "print_format_type",
    "html",
    "font_size",
    "margin_top",
    "margin_bottom",
    "margin_left",
    "margin_right",
    "disabled",
]


def ensure_print_formats():
    for parts in PRINT_FORMATS:
        with open(frappe.get_app_path(*parts)) as f:
            data = json.load(f)
        fields = {k: data.get(k) for k in _PRINT_FIELDS}
        if frappe.db.exists("Print Format", data["name"]):
            # App-owned standard format: keep template in sync with repo.
            doc = frappe.get_doc("Print Format", data["name"])
            if doc.html != fields["html"]:
                doc.html = fields["html"]
                doc.save(ignore_permissions=True)
            continue
        frappe.get_doc({"doctype": "Print Format", **fields}).insert(ignore_permissions=True)


def ensure_settings():
    """Create the Single settings row with defaults on first run."""
    if not frappe.db.exists("DocType", "Lube Station Settings"):
        return
    from lube_station.lube_station.settings import DEFAULTS

    try:
        frappe.get_cached_doc("Lube Station Settings")
    except Exception:
        frappe.get_doc({"doctype": "Lube Station Settings", **DEFAULTS}).insert(ignore_permissions=True)


def ensure_all():
    from lube_station.lube_station.security.roles import ensure_roles

    ensure_roles()
    ensure_settings()
    ensure_print_formats()
