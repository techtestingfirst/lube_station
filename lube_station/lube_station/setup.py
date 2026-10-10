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
    {
        "name": "Lube Total Sales",
        "label": "Total Sales",
        "type": "Custom",
        "document_type": "Hosting Invoice",
        "method": "lube_station.lube_station.reports.metrics.total_sales",
        "module": "Lube Station",
    },
    {
        "name": "Lube Total Customers",
        "label": "Total Customers",
        "type": "Custom",
        "document_type": "Hosting Customer",
        "method": "lube_station.lube_station.reports.metrics.total_customers",
        "module": "Lube Station",
    },
    {
        "name": "Lube Unpaid Invoices",
        "label": "Unpaid Invoices",
        "type": "Custom",
        "document_type": "Hosting Invoice",
        "method": "lube_station.lube_station.reports.metrics.unpaid_invoices",
        "module": "Lube Station",
    },
    {
        "name": "Lube Unpaid Amount",
        "label": "Unpaid Amount",
        "type": "Custom",
        "document_type": "Hosting Invoice",
        "method": "lube_station.lube_station.reports.metrics.unpaid_value",
        "module": "Lube Station",
    },
]

DASHBOARD_CHARTS = [
    {
        "name": "Lube Services by Status",
        "chart_name": "Lube Services by Status",
        "currency": None,
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
        "timeseries": 1,
        "document_type": "Hosting Invoice",
        "based_on": "creation",
        "value_based_on": "total_due",
        "timespan": "Last Year",
        "time_interval": "Monthly",
        "type": "Line",
        "filters_json": "[]",
        "module": "Lube Station",
    },
    {
        "name": "Lube Daily Revenue",
        "chart_name": "Lube Daily Revenue",
        "chart_type": "Sum",
        "document_type": "Hosting Invoice",
        "based_on": "creation",
        "value_based_on": "total_due",
        "timespan": "Last Week",
        "time_interval": "Daily",
        "timeseries": 1,
        "type": "Line",
        "filters_json": "[]",
        "module": "Lube Station",
    },
    {
        "name": "Lube Daily Customers",
        "chart_name": "Lube Daily Customers",
        "currency": None,
        "chart_type": "Count",
        "document_type": "Hosting Customer",
        "based_on": "creation",
        "timespan": "Last Week",
        "time_interval": "Daily",
        "timeseries": 1,
        "type": "Bar",
        "filters_json": "[]",
        "module": "Lube Station",
    },
    {
        "name": "Lube Daily Services",
        "chart_name": "Lube Daily Services",
        "currency": None,
        "chart_type": "Count",
        "document_type": "Service",
        "based_on": "creation",
        "timespan": "Last Week",
        "time_interval": "Daily",
        "timeseries": 1,
        "type": "Bar",
        "filters_json": "[]",
        "module": "Lube Station",
    },
    {
        "name": "Lube Daily Invoices",
        "chart_name": "Lube Daily Invoices",
        "currency": None,
        "chart_type": "Count",
        "document_type": "Hosting Invoice",
        "based_on": "creation",
        "timespan": "Last Week",
        "time_interval": "Daily",
        "timeseries": 1,
        "type": "Bar",
        "filters_json": "[]",
        "module": "Lube Station",
    },
]


REVENUE_CHARTS = {"Lube Daily Revenue", "Lube Invoice Revenue"}


def ensure_dashboard():
    """Seed seller command-center cards/charts. Idempotent: skips existing."""
    for card in NUMBER_CARDS:
        if frappe.db.get_value("Number Card", {"label": card["label"]}, "name"):
            continue
        data = {k: v for k, v in card.items() if k != "name"}
        frappe.get_doc({"doctype": "Number Card", "is_public": 1, **data}).insert(ignore_permissions=True)
    for chart in DASHBOARD_CHARTS:
        name = chart["name"]
        if frappe.db.exists("Dashboard Chart", name):
            doc = frappe.get_doc("Dashboard Chart", name)
            updated = False
            for key in ("timespan", "time_interval", "timeseries", "currency", "type", "chart_type", "based_on", "value_based_on",
                        "group_by_based_on", "group_by_type", "filters_json", "module"):
                if key not in chart:
                    continue
                if doc.get(key) != chart.get(key):
                    doc.set(key, chart.get(key))
                    updated = True
            if updated:
                doc.save(ignore_permissions=True)
            continue
        frappe.get_doc({"doctype": "Dashboard Chart", "is_public": 1, **chart}).insert(ignore_permissions=True)
    # Revenue charts keep the site default currency; count charts stay currency-free.
    default_currency = frappe.db.get_default("currency")
    for name in REVENUE_CHARTS:
        if default_currency and not frappe.db.get_value("Dashboard Chart", name, "currency"):
            frappe.db.set_value("Dashboard Chart", name, "currency", default_currency)
    # Sync the staff workspaces (home command-center + setup) into the DB.
    from frappe.modules.import_file import import_file_by_path

    for ws in ("lube_home/lube_home", "lube_station_home/lube_station_home"):
        import_file_by_path(
            frappe.get_app_path("lube_station", "lube_station", "workspace", *ws.split("/")) + ".json",
            force=True,
        )


def ensure_all():
    from lube_station.lube_station.security.roles import ensure_roles

    ensure_roles()
    ensure_settings()
    ensure_print_formats()
    ensure_dashboard()
