import frappe

from .guards import assert_owns, my_customer


@frappe.whitelist(methods=["GET"], allow_guest=True)
def storefront():
    plans = frappe.get_all("Hosting Plan", {"is_active": 1}, ["name", "plan_name", "product_type", "product_group"])
    out = []
    for p in plans:
        prices = frappe.get_all("Plan Pricing", {"hosting_plan": p.name}, ["billing_cycle", "recurring_amount", "setup_fee"])
        out.append({**p, "prices": prices})
    return out


@frappe.whitelist(methods=["GET"])
def dashboard():
    customer = my_customer()
    return {
        "services": frappe.db.count("Service", {"customer": customer}),
        "unpaid": frappe.db.count("Hosting Invoice", {"customer": customer, "status": "Unpaid"}),
        "domains": frappe.db.count("Domain", {"customer": customer}),
        "tickets": frappe.db.count("Ticket Hosting Reference", {"customer": customer}),
    }


@frappe.whitelist(methods=["GET"])
def checkout_info(plan: str):
    schema = frappe.db.get_value("Hosting Plan", plan, "product_type_schema")
    prices = frappe.get_all("Plan Pricing", {"hosting_plan": plan}, ["billing_cycle", "recurring_amount", "setup_fee"])
    requirements = None
    if schema:
        from lube_station.lube_station.doctype.product_type_schema.product_type_schema import get_product_requirements

        requirements = get_product_requirements(plan=plan)
    return {"prices": prices, "requirements": requirements}


@frappe.whitelist(methods=["GET"])
def my_invoices():
    customer = my_customer()
    return frappe.get_all("Hosting Invoice", {"customer": customer}, ["name", "total_due", "status", "due_date"])


@frappe.whitelist(methods=["GET"])
def my_services():
    customer = my_customer()
    return frappe.get_all("Service", {"customer": customer}, ["name", "hosting_plan", "status", "next_due_date"])


@frappe.whitelist(methods=["GET"])
def my_domains():
    customer = my_customer()
    return frappe.get_all("Domain", {"customer": customer}, ["domain_name", "status", "expiry_date"])


@frappe.whitelist(methods=["GET"])
def dns_list(domain: str):
    dom = frappe.get_doc("Domain", domain)
    assert_owns(dom.customer)
    return frappe.get_all("DNS Record", {"domain": domain}, ["name", "record_type", "hostname", "record_value", "ttl"])


@frappe.whitelist(methods=["POST"])
def vps_control(instance: str, action: str, arg: str | None = None):
    from lube_station.lube_station.doctype.vps_instance.vps_instance import vps_action

    return vps_action(instance, action, arg)


@frappe.whitelist(methods=["GET"])
def downloads():
    from lube_station.lube_station.doctype.downloadable_asset.downloadable_asset import check_entitlement

    assets = frappe.get_all("Downloadable Asset", {"active": 1}, ["name", "title", "access_policy"])
    return [a for a in assets if check_entitlement(a.name)["allowed"]]


@frappe.whitelist(methods=["GET"])
def my_account():
    customer = my_customer()
    return frappe.get_doc("Hosting Customer", customer).as_dict()
