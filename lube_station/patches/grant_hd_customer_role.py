"""Backfill HD Customer role for pre-existing Hosting Customer users.

New signups get it in signup_customer. Without it, the Helpdesk customer
portal (/helpdesk/my-tickets/<ticket>) denies HD Ticket read, breaking the
"Open in Helpdesk" deep link from the Lube portal.
Idempotent: only appends when the role exists (helpdesk installed) and missing.
Runs post-model-sync.
"""

import frappe


def execute():
    if not frappe.db.exists("Role", "HD Customer"):
        return
    if not frappe.db.exists("DocType", "Hosting Customer"):
        return
    users = frappe.db.get_all("Hosting Customer", pluck="user")
    for user in {u for u in users if u}:
        if frappe.db.exists("Has Role", {"parent": user, "role": "HD Customer"}):
            continue
        try:
            frappe.get_doc("User", user).add_roles("HD Customer")
        except Exception:
            continue
