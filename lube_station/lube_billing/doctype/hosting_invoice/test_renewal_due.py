import uuid

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import add_days, getdate, today

from lube_station.lube_billing.doctype.hosting_invoice.hosting_invoice import generate_invoice, generate_renewal
from lube_station.lube_customers.doctype.order.order import place_order


def _setup(prefix: str):
    email = f"{prefix}-{uuid.uuid4().hex[:8]}@test.com"
    user = frappe.get_doc({"doctype": "User", "email": email, "first_name": "Due", "enabled": 1}).insert(ignore_permissions=True)
    cust = frappe.get_doc({"doctype": "Hosting Customer", "user": user.name, "status": "Active"}).insert()
    group = frappe.get_doc({"doctype": "Product Group", "group_name": f"{prefix} Group"}).insert()
    plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": f"{prefix} Plan", "product_group": group.name, "product_type": "Shared Hosting", "is_active": 1}).insert()
    frappe.get_doc({"doctype": "Plan Pricing", "hosting_plan": plan.name, "billing_cycle": "Monthly", "recurring_amount": 80}).insert()
    cart = frappe.get_doc({"doctype": "Cart", "customer": cust.name, "session_id": f"{prefix}-1"}).insert()
    cart.append("items", {"item_type": "Hosting Plan", "hosting_plan": plan.name, "billing_cycle": "Monthly", "quantity": 1})
    cart.save()
    out = place_order(cart.name, cust.name)
    return cust, out["order"]


class TestWhmcsDueDates(IntegrationTestCase):
    def test_initial_due_on_receipt(self):
        _, order = _setup("dueinit")
        inv = frappe.get_doc("Hosting Invoice", generate_invoice(order)["invoice"])
        self.assertEqual(str(inv.due_date), str(today()))

    def test_renewal_due_on_next_due_date(self):
        from lube_station.lube_provisioning.doctype.service.service import create_from_order

        _, order = _setup("dueren")
        create_from_order(order)
        svc = frappe.db.get_value("Service", {"order_ref": order}, "name")
        target = add_days(today(), 20)
        frappe.db.set_value("Service", svc, {"status": "Active", "next_due_date": target})
        inv = frappe.get_doc("Hosting Invoice", generate_renewal(order, "2099-01")["invoice"])
        self.assertEqual(str(inv.due_date), str(target))

    def test_renewal_payment_advances_next_due(self):
        from lube_station.lube_provisioning.doctype.service.service import create_from_order, on_invoice_paid

        _, order = _setup("dueadv")
        create_from_order(order)
        svc = frappe.db.get_value("Service", {"order_ref": order}, "name")
        frappe.db.set_value("Service", svc, {"status": "Active", "next_due_date": add_days(today(), 20), "billing_cycle": "Monthly"})
        inv = frappe.get_doc("Hosting Invoice", generate_renewal(order, "2099-02")["invoice"])
        inv.status = "Paid"
        inv.save()
        on_invoice_paid(inv.name)
        advanced = frappe.db.get_value("Service", svc, "next_due_date")
        # One full Monthly cycle forward from the previous next-due date.
        from frappe.utils import add_to_date

        self.assertEqual(str(advanced), str(getdate(add_to_date(getdate(add_days(today(), 20)), months=1))))

    def test_cron_window_and_idempotency(self):
        from lube_station.lube_provisioning.doctype.service.service import create_from_order, generate_upcoming_renewals

        _, order = _setup("duecron")
        create_from_order(order)
        svc = frappe.db.get_value("Service", {"order_ref": order}, "name")
        frappe.db.set_value("Service", svc, {"status": "Active", "next_due_date": add_days(today(), 5)})
        first = generate_upcoming_renewals()
        self.assertEqual(len(first["invoices"]), 1)
        inv = frappe.get_doc("Hosting Invoice", first["invoices"][0])
        self.assertEqual(str(inv.due_date), str(add_days(today(), 5)))
        again = generate_upcoming_renewals()
        self.assertEqual(again["invoices"], [])
        # Far-future and overdue services are skipped.
        frappe.db.set_value("Service", svc, "next_due_date", add_days(today(), 90))
        self.assertEqual(generate_upcoming_renewals()["invoices"], [])
        frappe.db.set_value("Service", svc, "next_due_date", add_days(today(), -3))
        self.assertEqual(generate_upcoming_renewals()["invoices"], [])
