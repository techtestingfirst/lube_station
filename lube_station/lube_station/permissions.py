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


def has_customer_document_permission(doc, user=None, ptype="read", debug=False) -> bool:
    """Row check: Customer role may access own rows, nothing else.

    Arg order keeps backward compat with direct (doc, user) calls;
    Frappe's hook caller passes doc/ptype/user as kwargs.
    """
    user = user or frappe.session.user
    if "System Manager" in frappe.get_roles(user):
        return True
    linked = _linked_customer(user)
    return bool(linked and doc.get("customer") == linked)


hosting_invoice_query = customer_document_query("Hosting Invoice")
order_query = customer_document_query("Order")
cart_query = customer_document_query("Cart")
kyc_query = customer_document_query("Customer KYC Verification")
domain_query = customer_document_query("Registered Domain")
payment_method_query = customer_document_query("Saved Payment Method")


def vps_instance_query(user=None):
    """List filter: customers see only instances under their own Orders.

    Orphan rows (empty order_ref) match nothing: fail closed.
    """
    user = user or frappe.session.user
    if "System Manager" in frappe.get_roles(user):
        return ""
    linked = _linked_customer(user)
    if not linked:
        return "1=0"
    esc = frappe.db.escape(linked)
    return (
        "`tabVPS Instance`.`order_ref` in "
        f"(select `name` from `tabOrder` where `customer` = {esc})"
    )


def has_vps_instance_permission(doc, user=None, ptype="read", debug=False) -> bool:
    """Row check: instance is visible only via an owned Order. No order = deny."""
    user = user or frappe.session.user
    if "System Manager" in frappe.get_roles(user):
        return True
    linked = _linked_customer(user)
    if not linked:
        return False
    order_ref = doc.get("order_ref")
    if not order_ref:
        return False
    return frappe.db.get_value("Order", order_ref, "customer") == linked


def dns_record_query(user=None):
    """List filter: customers see only records under their own domains."""
    user = user or frappe.session.user
    if "System Manager" in frappe.get_roles(user):
        return ""
    linked = _linked_customer(user)
    if not linked:
        return "1=0"
    esc = frappe.db.escape(linked)
    return (
        "`tabDNS Record`.`domain` in "
        f"(select `name` from `tabRegistered Domain` where `customer` = {esc})"
    )


def has_dns_record_permission(doc, user=None, ptype="read", debug=False) -> bool:
    """Row check: record is visible only via an owned domain. No domain = deny."""
    user = user or frappe.session.user
    if "System Manager" in frappe.get_roles(user):
        return True
    linked = _linked_customer(user)
    if not linked:
        return False
    domain = doc.get("domain")
    if not domain:
        return False
    return frappe.db.get_value("Registered Domain", domain, "customer") == linked


STAFF_ROLES = {"System Manager", "Support Agent", "Billing Admin", "Provisioning Operator"}


def has_app_permission() -> bool:
    """App tile gate for /apps screen: staff only. Customers use /store."""
    user = frappe.session.user
    if not user or user == "Guest":
        return False
    if user == "Administrator":
        return True
    return bool(STAFF_ROLES.intersection(frappe.get_roles(user)))
