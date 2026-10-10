import frappe


def hosting_customer_query(user=None):
    user = user or frappe.session.user
    if "System Manager" in frappe.get_roles(user):
        return ""
    linked = frappe.db.get_value("Hosting Customer", {"user": user}, "name")
    if not linked:
        return "1=0"
    return f"`tabHosting Customer`.`name` = {frappe.db.escape(linked)}"


def _linked_customer(user=None) -> str | None:
    user = user or frappe.session.user
    if user in (None, "", "Guest"):
        return None
    return frappe.db.get_value("Hosting Customer", {"user": user}, "name")


def customer_document_query(doctype):
    """List filter: customers see only their own rows, staff see all."""

    def query(user=None):
        user = user or frappe.session.user
        if "System Manager" in frappe.get_roles(user):
            return ""
        linked = _linked_customer(user)
        if not linked:
            return "1=0"
        return f"`tab{doctype}`.`customer` = {frappe.db.escape(linked)}"

    return query


def has_customer_document_permission(doc, user=None) -> bool:
    """Row check: Customer role may read/print own invoices, nothing else."""
    user = user or frappe.session.user
    if "System Manager" in frappe.get_roles(user):
        return True
    linked = _linked_customer(user)
    return bool(linked and doc.get("customer") == linked)


hosting_invoice_query = customer_document_query("Hosting Invoice")


STAFF_ROLES = {"System Manager", "Support Agent", "Billing Admin", "Provisioning Operator"}


def has_app_permission() -> bool:
    """App tile gate for /apps screen: staff only. Customers use /store."""
    user = frappe.session.user
    if not user or user == "Guest":
        return False
    if user == "Administrator":
        return True
    return bool(STAFF_ROLES.intersection(frappe.get_roles(user)))
