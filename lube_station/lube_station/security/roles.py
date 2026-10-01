import frappe

ROLES = ["Customer", "Support Agent", "Billing Admin", "Provisioning Operator"]


def ensure_roles():
    for name in ROLES:
        if not frappe.db.exists("Role", name):
            frappe.get_doc({"doctype": "Role", "role_name": name, "desk_access": 1}).insert(ignore_permissions=True)
