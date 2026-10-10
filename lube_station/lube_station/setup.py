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


NUMBER_CARDS = [
    {
        "name": "Lube MRR",
        "label": "MRR",
        "type": "Custom",
        "document_type": "Service",
        "method": "lube_station.lube_station.reports.metrics.mrr_value",
        "module": "Lube Station",
    },
    {
        "name": "Lube Overdue Receivable",
        "label": "Overdue Receivable",
        "type": "Custom",
        "document_type": "Hosting Invoice",
        "method": "lube_station.lube_station.reports.metrics.overdue_value",
        "module": "Lube Station",
    },
    {
        "name": "Lube Active Services",
        "label": "Active Services",
        "type": "Custom",
        "document_type": "Service",
        "method": "lube_station.lube_station.reports.metrics.active_services",
        "module": "Lube Station",
    },
    {
        "name": "Lube Churn Rate",
        "label": "Churn Rate",
        "type": "Custom",
        "document_type": "Service",
        "method": "lube_station.lube_station.reports.metrics.churn_rate",
        "module": "Lube Station",
    },
]

DASHBOARD_CHARTS = [
    {
        "name": "Lube Services by Status",
        "chart_name": "Lube Services by Status",
        "chart_type": "Group By",
        "document_type": "Service",
        "group_by_based_on": "status",
        "group_by_type": "Count",
        "type": "Bar",
        "filters_json": "[]",
        "module": "Lube Station",
    },
    {
        "name": "Lube Invoice Revenue",
        "chart_name": "Lube Invoice Revenue",
        "chart_type": "Sum",
        "document_type": "Hosting Invoice",
        "based_on": "creation",
        "value_based_on": "total_due",
        "timespan": "Last Year",
        "time_interval": "Monthly",
        "type": "Line",
        "filters_json": "[]",
        "module": "Lube Station",
    },
]


def ensure_dashboard():
    """Seed seller command-center cards/charts. Idempotent: skips existing."""
    for card in NUMBER_CARDS:
        if frappe.db.get_value("Number Card", {"label": card["label"]}, "name"):
            continue
        data = {k: v for k, v in card.items() if k != "name"}
        frappe.get_doc({"doctype": "Number Card", "is_public": 1, **data}).insert(ignore_permissions=True)
    for chart in DASHBOARD_CHARTS:
        if frappe.db.exists("Dashboard Chart", chart["name"]):
            continue
        frappe.get_doc({"doctype": "Dashboard Chart", "is_public": 1, **chart}).insert(ignore_permissions=True)
    # Sync the staff command-center workspace file into the DB.
    from frappe.modules.import_file import import_file_by_path

    import_file_by_path(
        frappe.get_app_path("lube_station", "lube_station", "workspace", "lube_station_home", "lube_station_home.json"),
        force=True,
    )


def ensure_all():
    from lube_station.lube_station.security.roles import ensure_roles

    ensure_roles()
    ensure_settings()
    ensure_print_formats()
    ensure_dashboard()
