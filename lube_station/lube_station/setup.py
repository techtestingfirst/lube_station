"""Idempotent setup: print formats and other seeded records."""

import json

import frappe

# (schema_name, product_type, flags, requirement fields).
# Contract: lube_station/tests/test_product_schemas.py. 11 types per spec.
PRODUCT_TYPE_SCHEMAS = [
    (
        "Shared Hosting Default",
        "Shared Hosting",
        {"requires_domain": 1},
        [{"field_key": "domain", "label": "Domain", "field_type": "Text", "required": 1}],
    ),
    (
        "Reseller Default",
        "Reseller",
        {"requires_domain": 1},
        [{"field_key": "domain", "label": "Domain", "field_type": "Text", "required": 1}],
    ),
    (
        "VPS Default",
        "VPS",
        {"requires_hostname": 1, "requires_root_password": 1, "requires_os": 1, "requires_location": 1},
        [
            {"field_key": "hostname", "label": "Hostname", "field_type": "Text", "required": 1},
            {"field_key": "os", "label": "OS", "field_type": "Select", "required": 1},
            {"field_key": "location", "label": "Location", "field_type": "Text", "required": 0},
        ],
    ),
    (
        "Dedicated Server Default",
        "Dedicated Server",
        {"requires_hostname": 1, "requires_root_password": 1, "requires_os": 1, "requires_location": 1},
        [
            {"field_key": "hostname", "label": "Hostname", "field_type": "Text", "required": 1},
            {"field_key": "os", "label": "OS", "field_type": "Select", "required": 1},
        ],
    ),
    (
        "Cloud Default",
        "Cloud",
        {"requires_hostname": 1, "requires_os": 1, "requires_location": 1},
        [
            {"field_key": "hostname", "label": "Hostname", "field_type": "Text", "required": 1},
            {"field_key": "os", "label": "OS", "field_type": "Select", "required": 1},
        ],
    ),
    (
        "Email Hosting Default",
        "Email Hosting",
        {"requires_domain": 1},
        [{"field_key": "domain", "label": "Domain", "field_type": "Text", "required": 1}],
    ),
    (
        "Website Builder Default",
        "Website Builder",
        {"requires_domain": 1},
        [{"field_key": "domain", "label": "Domain", "field_type": "Text", "required": 1}],
    ),
    (
        "SSL Default",
        "SSL",
        {},
        [
            {"field_key": "common_name", "label": "Common Name", "field_type": "Text", "required": 1},
            {"field_key": "approver_email", "label": "Approver Email", "field_type": "Text", "required": 1},
        ],
    ),
    ("Backup Addon Default", "Backup Addon", {}, []),
    (
        "Migration Service Default",
        "Migration Service",
        {},
        [{"field_key": "source_host", "label": "Source Host", "field_type": "Text", "required": 1}],
    ),
    ("Downloadable Product Default", "Downloadable Product", {}, []),
]


def ensure_product_schemas():
    """Seed the 11 default type schemas. Never overwrites existing rows."""
    for schema_name, product_type, flags, fields in PRODUCT_TYPE_SCHEMAS:
        if frappe.db.exists("Product Type Schema", schema_name):
            continue
        frappe.get_doc(
            {
                "doctype": "Product Type Schema",
                "schema_name": schema_name,
                "product_type": product_type,
                **flags,
                "fields": fields,
            }
        ).insert(ignore_permissions=True)


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
    # Sync the staff workspaces (home command-center + setup + customers queue) into the DB.
    from frappe.modules.import_file import import_file_by_path

    for ws in ("lube_home/lube_home", "lube_station_home/lube_station_home", "lube_customers/lube_customers"):
        import_file_by_path(
            frappe.get_app_path("lube_station", "lube_station", "workspace", *ws.split("/")) + ".json",
            force=True,
        )


def ensure_email_templates():
    """Seed default Lube Email Templates. Never overwrites seller edits."""
    from lube_station.lube_station.notifications.events import TEMPLATES

    if not frappe.db.exists("DocType", "Email Template"):
        return
    for event_type, subject in TEMPLATES.items():
        name = f"Lube {event_type.replace('_', ' ').title()}"
        if frappe.db.exists("Email Template", name):
            continue
        body = (
            f"{subject}\n\nReference: {{{{ reference }}}}\n"
            "Event: {{ event }}\n"
            "Login to your client area for details."
        )
        # Domain/service/invoice specifics render when callers pass them.
        body += "\n{% if service %}Service: {{ service }}{% endif %}{% if domain %}Domain: {{ domain }}{% endif %}{% if invoice %}Invoice: {{ invoice }}{% endif %}{% if amount %}Amount: {{ amount }}{% endif %}"
        try:
            frappe.get_doc({"doctype": "Email Template", "name": name, "subject": f"{subject} {{{{ reference }}}}", "response": body}).insert(ignore_permissions=True)
        except Exception:
            continue


def ensure_all():
    from lube_station.lube_station.security.roles import ensure_roles

    ensure_roles()
    ensure_settings()
    from lube_station.lube_station.adapters.seed import seed

    seed()
    ensure_print_formats()
    ensure_product_schemas()
    ensure_email_templates()
    ensure_dashboard()
    ensure_sso_flags()
    ensure_service_servers()


def ensure_sso_flags():
    """One-way enablement: MVP panels support single-click login."""
    if not frappe.db.exists("DocType", "Provisioning Adapter"):
        return
    for name in ("cPanel / WHM", "Plesk", "DirectAdmin"):
        try:
            if frappe.db.exists("Provisioning Adapter", name):
                frappe.db.set_value("Provisioning Adapter", name, "supports_sso", 1)
        except Exception:
            continue


def ensure_service_servers(limit: int = 500):
    """Backfill server + username for services created before assignment.

    Idempotent: fills null/empty values and repairs panel mismatches
    (server panel != module panel). New orders are covered in
    create_from_order; this heals demo/history data so the panel-login
    button has something to work with.
    """
    from lube_station.lube_provisioning.doctype.service.service import _make_username, _module_panel, _pick_server_for_plan

    try:
        rows = frappe.get_all(
            "Service",
            {},
            ["name", "hosting_plan", "primary_domain", "status", "server", "svc_username"],
            limit=limit,
        )
    except Exception:
        return
    for r in rows:
        try:
            product_type = frappe.db.get_value("Hosting Plan", r.get("hosting_plan"), "product_type")
            want_user = product_type in ("Shared Hosting", "Reseller", "Email Hosting", "Website Builder")
            server = (r.get("server") or "").strip()
            needs_server = not server
            if server and want_user:
                want_panel = _module_panel(r.get("hosting_plan"))
                have_panel = frappe.db.get_value("Server", server, "control_panel")
                if want_panel and have_panel and want_panel != have_panel:
                    needs_server = True
            if needs_server:
                picked = _pick_server_for_plan(r.get("hosting_plan"))
                if picked:
                    frappe.db.set_value("Service", r.name, "server", picked)
            if want_user and not (r.get("svc_username") or "").strip():
                frappe.db.set_value("Service", r.name, "svc_username", _make_username(r.get("primary_domain")))
        except Exception:
            continue
