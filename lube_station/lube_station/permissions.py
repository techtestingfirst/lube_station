import frappe


def hosting_customer_query(user=None):
    user = user or frappe.session.user
    if "System Manager" in frappe.get_roles(user):
        return ""
    linked = frappe.db.get_value("Hosting Customer", {"user": user}, "name")
    if not linked:
        return "1=0"
    return f"`tabHosting Customer`.`name` = {frappe.db.escape(linked)}"
