"""Promote free-text plan tax codes to Tax Code masters.

Hosting Plan.tax_code changed Data -> Link (Tax Code, named by code), so
distinct existing strings become master records; plan links resolve by name
and keep working without edits. Idempotent.
"""

import frappe


def execute():
    if not frappe.db.exists("DocType", "Tax Code"):
        return
    if not frappe.db.exists("DocType", "Hosting Plan"):
        return
    codes = frappe.db.get_all("Hosting Plan", {"tax_code": ["!=", ""]}, pluck="tax_code")
    for code in {str(c).strip() for c in codes if c and str(c).strip()}:
        if frappe.db.exists("Tax Code", code):
            continue
        try:
            frappe.get_doc({"doctype": "Tax Code", "code": code}).insert(ignore_permissions=True)
        except Exception:
            continue
