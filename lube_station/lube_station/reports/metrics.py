import frappe


@frappe.whitelist(methods=["GET"])
def mrr() -> dict:
    rows = frappe.db.sql("select billing_cycle, sum(recurring_amount) total from `tabService` where status='Active' group by billing_cycle", as_dict=True)
    monthly = {"Monthly": 1, "Quarterly": 1 / 3, "Semi-Annually": 1 / 6, "Annually": 1 / 12, "Biennially": 1 / 24, "Triennially": 1 / 36, "One Time": 0}
    total = sum((r.total or 0) * monthly.get(r.billing_cycle, 0) for r in rows)
    return {"mrr": round(total, 2), "by_cycle": rows}


@frappe.whitelist(methods=["GET"])
def overdue_aging() -> dict:
    rows = frappe.db.sql("select status, count(*) c, sum(total_due) t from `tabHosting Invoice` group by status", as_dict=True)
    return {"buckets": rows}


@frappe.whitelist(methods=["GET"])
def churn() -> dict:
    total = frappe.db.count("Service")
    lost = frappe.db.count("Service", {"status": ["in", ["Terminated", "Cancelled"]]})
    return {"total": total, "lost": lost, "rate": round(lost / total, 4) if total else 0}


@frappe.whitelist(methods=["GET"])
def service_inventory() -> dict:
    return {"by_status": frappe.db.sql("select status, count(*) c from `tabService` group by status", as_dict=True)}


@frappe.whitelist(methods=["GET"])
def product_revenue() -> dict:
    return {"rows": frappe.db.sql("select hosting_plan, sum(total_due) t from `tabHosting Invoice` group by hosting_plan", as_dict=True)}


@frappe.whitelist(methods=["GET"])
def download_report() -> dict:
    return {"rows": frappe.db.sql("select asset, count(*) c from `tabDownload Log` group by asset", as_dict=True)}


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
