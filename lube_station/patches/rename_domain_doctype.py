"""Rename Lube Station's "Domain" DocType to "Registered Domain".

Site history: "Domain" collided with Frappe core's DocType of the same name
(frappe/core/doctype/domain) and our sync overwrote core's definition.
The rename frees "Domain" so model sync restores core's DocType + table.
Runs pre-model-sync: code already references "Registered Domain", and the
post-rename sync recreates core's table from its own JSON.
"""

import frappe
from frappe.modules.import_file import import_file_by_path


def execute():
    if frappe.db.exists("DocType", "Registered Domain"):
        return
    if not frappe.db.exists("DocType", "Domain"):
        return
    # Guard: only rename our DocType, never core's.
    if frappe.db.get_value("DocType", "Domain", "module") != "Lube Domains":
        return
    frappe.rename_doc("DocType", "Domain", "Registered Domain", force=True)
    import_file_by_path(frappe.get_app_path("frappe", "core", "doctype", "domain", "domain.json"))
