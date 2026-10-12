import frappe
from frappe.tests import IntegrationTestCase


def _customer():
    name = frappe.db.get_value("Hosting Customer", {"user": "Administrator"}, "name")
    if name:
        frappe.db.set_value("Hosting Customer", name, "kyc_status", "Verified")
        return frappe.get_doc("Hosting Customer", name)
    return frappe.get_doc({"doctype": "Hosting Customer", "user": "Administrator", "status": "Active", "kyc_status": "Verified"}).insert()


def _plan():
    name = frappe.db.get_value("Hosting Plan", {"plan_name": "Bridge Plan"}, "name")
    if name:
        return frappe.get_doc("Hosting Plan", name)
    group_name = frappe.db.get_value("Product Group", {"group_name": "Bridge Group"}, "name")
    if not group_name:
        group_name = frappe.get_doc({"doctype": "Product Group", "group_name": "Bridge Group"}).insert().name
    plan = frappe.get_doc(
        {
            "doctype": "Hosting Plan",
            "plan_name": "Bridge Plan",
            "product_group": group_name,
            "product_type": "Shared Hosting",
            "is_active": 1,
        }
    ).insert()
    if not frappe.db.exists("Plan Pricing", {"hosting_plan": plan.name, "billing_cycle": "Monthly"}):
        frappe.get_doc(
            {
                "doctype": "Plan Pricing",
                "hosting_plan": plan.name,
                "billing_cycle": "Monthly",
                "recurring_amount": 100,
            }
        ).insert()
    return plan


def _invoice(cust_name, amount=100, order=None):
    return frappe.get_doc(
        {
            "doctype": "Hosting Invoice",
            "customer": cust_name,
            "order_ref": order,
            "invoice_items": [{"description": "x", "amount": amount}],
            "status": "Unpaid",
        }
    ).insert(ignore_permissions=True)


class TestRazorpayBridge(IntegrationTestCase):
    def test_on_payment_authorized_marks_paid_and_activates(self):
        cust = _customer()
        plan = _plan()
        order = frappe.get_doc(
            {
                "doctype": "Order",
                "customer": cust.name,
                "status": "Pending Review",
                "items": [
                    {
                        "item_type": "Hosting Plan",
                        "reference": plan.name,
                        "billing_cycle": "Monthly",
                        "unit_price": 100,
                        "quantity": 1,
                    }
                ],
            }
        ).insert(ignore_permissions=True)
        inv = _invoice(cust.name, 100, order.name)
        svc = frappe.get_doc(
            {
                "doctype": "Service",
                "customer": cust.name,
                "hosting_plan": plan.name,
                "order_ref": order.name,
                "status": "Pending",
                "recurring_amount": 100,
            }
        ).insert(ignore_permissions=True)

        frappe.flags.data = {"razorpay_payment_id": "pay_bridge_1"}
        inv.on_payment_authorized("Completed")

        self.assertEqual(frappe.db.get_value("Hosting Invoice", inv.name, "status"), "Paid")
        self.assertEqual(frappe.db.get_value("Service", svc.name, "status"), "Active")
        self.assertTrue(frappe.db.exists("Payment Transaction", {"gateway_txn_id": "pay_bridge_1"}))

        # repeat callback is idempotent, no duplicate transaction
        inv.reload()
        inv.on_payment_authorized("Completed")
        self.assertEqual(
            frappe.db.count("Payment Transaction", {"gateway_txn_id": "pay_bridge_1"}), 1
        )

    def test_repeat_callback_with_existing_txn_still_fulfills(self):
        cust = _customer()
        plan = _plan()
        order = frappe.get_doc(
            {
                "doctype": "Order",
                "customer": cust.name,
                "status": "Pending Review",
                "items": [
                    {
                        "item_type": "Hosting Plan",
                        "reference": plan.name,
                        "billing_cycle": "Monthly",
                        "unit_price": 100,
                        "quantity": 1,
                    }
                ],
            }
        ).insert(ignore_permissions=True)
        inv = _invoice(cust.name, 100, order.name)
        svc = frappe.get_doc(
            {
                "doctype": "Service",
                "customer": cust.name,
                "hosting_plan": plan.name,
                "order_ref": order.name,
                "status": "Pending",
                "recurring_amount": 100,
            }
        ).insert(ignore_permissions=True)
        # Gateway retried the webhook: transaction row already stored,
        # invoice never marked Paid, fulfillment never ran.
        frappe.get_doc(
            {
                "doctype": "Payment Transaction",
                "invoice": inv.name,
                "gateway": "Razorpay",
                "gateway_txn_id": "pay_bridge_retry_1",
                "amount": 100,
                "status": "Success",
                "raw_response": "{}",
            }
        ).insert(ignore_permissions=True)

        frappe.flags.data = {"razorpay_payment_id": "pay_bridge_retry_1"}
        inv.reload()
        inv.on_payment_authorized("Completed")

        self.assertEqual(frappe.db.get_value("Hosting Invoice", inv.name, "status"), "Paid")
        self.assertEqual(frappe.db.get_value("Service", svc.name, "status"), "Active")
        self.assertTrue(frappe.db.exists("Notification Event", {"event_key": f"payment:{inv.name}"}))

    def test_on_payment_authorized_stripe(self):
        cust = _customer()
        inv = _invoice(cust.name, 50)

        frappe.flags.data = {"stripe_token_id": "tok_bridge_1"}
        inv.on_payment_authorized("Completed")

        self.assertEqual(frappe.db.get_value("Hosting Invoice", inv.name, "status"), "Paid")
        txn = frappe.db.get_value(
            "Payment Transaction", {"gateway_txn_id": "tok_bridge_1"}, ["gateway", "amount"]
        )
        self.assertEqual(txn[0], "Stripe")

    def test_on_payment_authorized_paypal(self):
        cust = _customer()
        inv = _invoice(cust.name, 60)

        frappe.flags.data = {"transaction_id": "PAY-BRIDGE-1"}
        inv.on_payment_authorized("Completed")

        self.assertEqual(frappe.db.get_value("Hosting Invoice", inv.name, "status"), "Paid")
        txn = frappe.db.get_value(
            "Payment Transaction", {"gateway_txn_id": "PAY-BRIDGE-1"}, ["gateway", "amount"]
        )
        self.assertEqual(txn[0], "PayPal")

    def test_paypal_link_rejected_for_inr(self):
        from lube_station.lube_station.adapters.seed import seed
        from lube_station.lube_station.payments.links import payment_link

        seed()
        cust = _customer()
        inv = _invoice(cust.name, 70)
        self.assertRaises(frappe.ValidationError, payment_link, inv.name, gateway="PayPal Checkout")
