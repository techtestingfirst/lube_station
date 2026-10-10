import frappe

STAFF_ROLES = {"System Manager", "Support Agent", "Billing Admin", "Provisioning Operator"}


def _require_staff():
    """Seller numbers are staff-only. Customers use /store portal APIs."""
    user = frappe.session.user
    if user == "Administrator":
        return
    if not user or user == "Guest" or not STAFF_ROLES.intersection(frappe.get_roles(user)):
        frappe.throw("Not permitted", frappe.PermissionError)


@frappe.whitelist(methods=["GET"])
def mrr() -> dict:
    _require_staff()
    rows = frappe.db.sql("select billing_cycle, sum(recurring_amount) total from `tabService` where status='Active' group by billing_cycle", as_dict=True)
    monthly = {"Monthly": 1, "Quarterly": 1 / 3, "Semi-Annually": 1 / 6, "Annually": 1 / 12, "Biennially": 1 / 24, "Triennially": 1 / 36, "One Time": 0}
    total = sum((r.total or 0) * monthly.get(r.billing_cycle, 0) for r in rows)
    return {"mrr": round(total, 2), "by_cycle": rows}


@frappe.whitelist(methods=["GET"])
def overdue_aging() -> dict:
    _require_staff()
    rows = frappe.db.sql("select status, count(*) c, sum(total_due) t from `tabHosting Invoice` group by status", as_dict=True)
    return {"buckets": rows}


@frappe.whitelist(methods=["GET"])
def churn() -> dict:
    _require_staff()
    total = frappe.db.count("Service")
    lost = frappe.db.count("Service", {"status": ["in", ["Terminated", "Cancelled"]]})
    return {"total": total, "lost": lost, "rate": round(lost / total, 4) if total else 0}


@frappe.whitelist(methods=["GET"])
def service_inventory() -> dict:
    _require_staff()
    return {"by_status": frappe.db.sql("select status, count(*) c from `tabService` group by status", as_dict=True)}


@frappe.whitelist(methods=["GET"])
def product_revenue() -> dict:
    _require_staff()
    return {"rows": frappe.db.sql("select hosting_plan, sum(total_due) t from `tabHosting Invoice` group by hosting_plan", as_dict=True)}


@frappe.whitelist(methods=["GET"])
def download_report() -> dict:
    _require_staff()
    return {"rows": frappe.db.sql("select asset, count(*) c from `tabDownload Log` group by asset", as_dict=True)}


@frappe.whitelist()
def mrr_value() -> float:
    """Scalar for Custom Number Card: monthly recurring revenue."""
    return mrr()["mrr"]


@frappe.whitelist()
def overdue_value() -> float:
    """Scalar for Custom Number Card: total due on Overdue invoices."""
    _require_staff()
    row = frappe.db.sql("select sum(total_due) t from `tabHosting Invoice` where status='Overdue'", as_dict=True)
    return float((row and row[0].t) or 0)


@frappe.whitelist()
def active_services() -> int:
    """Scalar for Custom Number Card: count of Active services."""
    _require_staff()
    return int(frappe.db.count("Service", {"status": "Active"}))


@frappe.whitelist()
def churn_rate() -> float:
    """Scalar for Custom Number Card: share of terminated/cancelled services."""
    return churn()["rate"]


@frappe.whitelist()
def total_sales() -> float:
    """Scalar for Custom Number Card: lifetime revenue on Paid invoices."""
    _require_staff()
    row = frappe.db.sql("select sum(total_due) t from `tabHosting Invoice` where status='Paid'", as_dict=True)
    return round(float((row and row[0].t) or 0), 2)


@frappe.whitelist()
def total_customers() -> int:
    """Scalar for Custom Number Card: count of hosting customers."""
    _require_staff()
    return int(frappe.db.count("Hosting Customer"))


@frappe.whitelist()
def unpaid_invoices() -> int:
    """Scalar for Custom Number Card: count of Unpaid + Overdue invoices."""
    _require_staff()
    return int(frappe.db.count("Hosting Invoice", {"status": ["in", ["Unpaid", "Overdue"]]}))


@frappe.whitelist()
def unpaid_value() -> float:
    """Scalar for Custom Number Card: amount due on Unpaid + Overdue invoices."""
    _require_staff()
    row = frappe.db.sql("select sum(total_due) t from `tabHosting Invoice` where status in ('Unpaid', 'Overdue')", as_dict=True)
    return round(float((row and row[0].t) or 0), 2)


@frappe.whitelist(methods=["POST"])
def credit_affiliate(affiliate: str, invoice: str) -> dict:
    inv = frappe.get_doc("Hosting Invoice", invoice)
    if inv.status != "Paid":
        return {"credited": False, "reason": "unpaid"}
    if frappe.db.exists("Affiliate Earning", {"invoice": invoice}):
        return {"credited": False, "reason": "duplicate"}
    aff = frappe.get_doc("Affiliate", affiliate)
    amount = round((inv.total_due or 0) * (aff.commission_percentage or 0) / 100, 2)
    frappe.get_doc({"doctype": "Affiliate Earning", "affiliate": affiliate, "invoice": invoice, "amount": amount}).insert(ignore_permissions=True)
    aff.total_earned = (aff.total_earned or 0) + amount
    aff.save(ignore_permissions=True)
    return {"credited": True, "amount": amount}
