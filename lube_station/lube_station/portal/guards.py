import frappe


def my_customer() -> str:
    user = frappe.session.user
    if user in (None, "", "Guest"):
        frappe.throw("Login required", frappe.PermissionError)
    name = frappe.db.get_value("Hosting Customer", {"user": user}, "name")
    if not name and "System Manager" not in frappe.get_roles(user):
        frappe.throw("No customer profile", frappe.PermissionError)
    return name


def assert_owns(customer: str):
    mine = my_customer()
    if "System Manager" in frappe.get_roles():
        return
    if mine != customer:
        frappe.throw("Cross-customer access denied", frappe.PermissionError)
