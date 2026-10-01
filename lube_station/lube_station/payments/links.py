import frappe

MVP_ORDER = ["Stripe", "Razorpay", "PayPal Checkout", "Bank Transfer"]


def pick_gateway(name: str | None = None) -> str:
    if name:
        record = frappe.get_doc("Payment Gateway Adapter", name)
        if not record.active:
            frappe.throw(f"{name} inactive")
        if not record.supports_one_time:
            frappe.throw(f"{name} lacks one-time support")
        return name
    for candidate in MVP_ORDER:
        if frappe.db.get_value("Payment Gateway Adapter", candidate, "active"):
            return candidate
    frappe.throw("No active one-time gateway")


@frappe.whitelist(methods=["GET", "POST"])
def payment_link(invoice: str, gateway: str | None = None) -> dict:
    inv = frappe.get_doc("Hosting Invoice", invoice)
    if inv.status == "Paid":
        frappe.throw("Invoice already paid")
    chosen = pick_gateway(gateway or inv.gateway)
    inv.gateway = chosen
    inv.save(ignore_permissions=True)
    if chosen == "Bank Transfer":
        return {"gateway": chosen, "manual": True, "instructions": "Transfer to account, attach reference"}
    return {"gateway": chosen, "url": f"/payments/{chosen.lower().replace(' ', '-')}/pay/{inv.name}", "amount": inv.total_due}
