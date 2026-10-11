import uuid

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.portal import apis


def _make_customer():
    """Unique customer per test: immune to leftover site data.

    Fixtures stay as Administrator; caller switches to the customer user
    only for the portal API calls under test.
    """
    email = f"portal-{uuid.uuid4().hex[:10]}@test.com"
    user = frappe.get_doc(
        {"doctype": "User", "email": email, "first_name": "Portal", "enabled": 1}
    ).insert(ignore_permissions=True)
    cust = frappe.get_doc({"doctype": "Hosting Customer", "user": user.name, "status": "Active"}).insert(
        ignore_permissions=True
    )
    return cust.name, user.name


class TestPortalApis(IntegrationTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")
        super().tearDown()

    def test_portal_apis(self):
        cust_name, user_name = _make_customer()
        group = frappe.get_doc({"doctype": "Product Group", "group_name": f"Portal Group {uuid.uuid4().hex[:6]}"}).insert()
        plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": f"Portal Plan {uuid.uuid4().hex[:6]}", "product_group": group.name, "product_type": "Shared Hosting", "is_active": 1}).insert()
        frappe.get_doc({"doctype": "Plan Pricing", "hosting_plan": plan.name, "billing_cycle": "Monthly", "recurring_amount": 10}).insert()
        frappe.get_doc({"doctype": "Service", "customer": cust_name, "hosting_plan": plan.name, "status": "Active", "recurring_amount": 10}).insert()
        frappe.set_user(user_name)
        store = apis.storefront()
        self.assertTrue(any(p["name"] == plan.name for p in store))
        dash = apis.dashboard()
        self.assertEqual(dash["services"], 1)
        info = apis.checkout_info(plan.name)
        self.assertTrue(info["prices"])
        invs = apis.my_invoices()
        self.assertIsInstance(invs, list)
        frappe.set_user("Guest")
        self.assertRaises(frappe.PermissionError, apis.dashboard)

    def test_my_service_detail(self):
        cust_name, user_name = _make_customer()
        group = frappe.get_doc({"doctype": "Product Group", "group_name": f"Portal Detail Group {uuid.uuid4().hex[:6]}"}).insert()
        plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": f"Portal Detail Plan {uuid.uuid4().hex[:6]}", "product_group": group.name, "product_type": "Shared Hosting", "is_active": 1}).insert()
        svc = frappe.get_doc({"doctype": "Service", "customer": cust_name, "hosting_plan": plan.name, "status": "Active", "recurring_amount": 10}).insert()
        frappe.set_user(user_name)
        detail = apis.my_service_detail(svc.name)
        self.assertEqual(detail["service"]["name"], svc.name)
        self.assertEqual(detail["service"]["status"], "Active")
        self.assertIsInstance(detail["invoices"], list)
        # WHMCS-parity enrichment: billing, configuration, capabilities present.
        for key in ("plan", "server", "billing", "configuration", "custom_fields", "hidden_count", "capabilities", "management_note", "vps_spec", "dedicated_spec"):
            self.assertIn(key, detail)
        self.assertIn("registration_date", detail["service"])
        self.assertIn("payment_method", detail["service"])
        self.assertIn("can_vps_control", detail["capabilities"])
        # Guest gets no customer profile.
        frappe.set_user("Guest")
        self.assertRaises(frappe.PermissionError, apis.my_service_detail, svc.name)
        # Another customer cannot read this service.
        stranger = frappe.get_doc(
            {"doctype": "User", "email": f"stranger-svc-{uuid.uuid4().hex[:6]}@test.com", "first_name": "Stranger", "enabled": 1}
        ).insert(ignore_permissions=True)
        frappe.get_doc({"doctype": "Hosting Customer", "user": stranger.name, "status": "Active"}).insert(
            ignore_permissions=True
        )
        frappe.set_user(stranger.name)
        self.assertRaises(frappe.PermissionError, apis.my_service_detail, svc.name)

    def test_my_service_detail_hides_secrets(self):
        cust_name, user_name = _make_customer()
        group = frappe.get_doc({"doctype": "Product Group", "group_name": f"Portal Secret Group {uuid.uuid4().hex[:6]}"}).insert()
        schema = frappe.get_doc(
            {
                "doctype": "Product Type Schema",
                "schema_name": f"Portal Secret Schema {uuid.uuid4().hex[:6]}",
                "product_type": "VPS",
                "fields": [
                    {"field_key": "hostname", "label": "Hostname", "field_type": "Text"},
                    {"field_key": "root_pass", "label": "Root Password", "field_type": "Password"},
                ],
            }
        ).insert()
        plan = frappe.get_doc(
            {
                "doctype": "Hosting Plan",
                "plan_name": f"Portal Secret Plan {uuid.uuid4().hex[:6]}",
                "product_group": group.name,
                "product_type": "VPS",
                "product_type_schema": schema.name,
                "is_active": 1,
            }
        ).insert()
        frappe.get_doc({"doctype": "Plan Pricing", "hosting_plan": plan.name, "billing_cycle": "Monthly", "recurring_amount": 20}).insert()
        cart = frappe.get_doc({"doctype": "Cart", "customer": cust_name}).insert(ignore_permissions=True)
        cart.append(
            "items",
            {
                "item_type": "Hosting Plan",
                "hosting_plan": plan.name,
                "billing_cycle": "Monthly",
                "quantity": 1,
                "configuration_json": '{"hostname": "vps1.test", "root_pass": "s3cret-root", "api_token": "abc123"}',
            },
        )
        cart.save(ignore_permissions=True)
        from lube_station.lube_customers.doctype.order.order import place_order

        order_name = place_order(cart.name, cust_name)["order"]
        svc = frappe.get_doc(
            {"doctype": "Service", "customer": cust_name, "hosting_plan": plan.name, "order_ref": order_name, "status": "Active", "recurring_amount": 20}
        ).insert()
        frappe.set_user(user_name)
        detail = apis.my_service_detail(svc.name)
        dumped = frappe.as_json(detail)
        self.assertNotIn("s3cret-root", dumped)
        self.assertNotIn("abc123", dumped)
        self.assertTrue(any(r["key"] == "hostname" for r in detail["custom_fields"]))
        self.assertGreaterEqual(detail["hidden_count"], 2)

    def test_my_invoice_detail(self):
        cust_name, user_name = _make_customer()
        frappe.db.set_value(
            "Hosting Customer",
            cust_name,
            {"company": "Acme Ltd", "phone": "+100000000", "tax_id": "VAT123", "address_line1": "1 Main St", "city": "Springfield", "country": "India"},
        )
        group = frappe.get_doc({"doctype": "Product Group", "group_name": f"Portal Inv Group {uuid.uuid4().hex[:6]}"}).insert()
        plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": f"Portal Inv Plan {uuid.uuid4().hex[:6]}", "product_group": group.name, "product_type": "Shared Hosting", "is_active": 1}).insert()
        svc = frappe.get_doc({"doctype": "Service", "customer": cust_name, "hosting_plan": plan.name, "status": "Active", "recurring_amount": 10, "primary_domain": "example.com"}).insert()
        inv = frappe.get_doc(
            {
                "doctype": "Hosting Invoice",
                "customer": cust_name,
                "invoice_items": [
                    {"description": f"Hosting Plan: {plan.name} x1", "service_ref": svc.name, "amount": 100},
                    {"description": f"Setup fee: {plan.name} x1", "service_ref": plan.name, "amount": 20},
                ],
                "status": "Unpaid",
            }
        ).insert()
        frappe.set_user(user_name)
        detail = apis.my_invoice_detail(inv.name)
        self.assertEqual(detail["invoice"]["name"], inv.name)
        self.assertEqual(len(detail["invoice"]["invoice_items"]), 2)
        # Service ref resolves to plan name + purchased domain, never raw IDs.
        first, second = detail["invoice"]["invoice_items"]
        self.assertEqual(first["plan_name"], plan.plan_name)
        self.assertEqual(first["domain"], "example.com")
        self.assertEqual(first["title"], plan.plan_name)
        self.assertEqual(first["meta"], f"Hosting Plan: {group.name} {plan.plan_name} x1")
        self.assertNotIn(svc.name, (first["title"], first["meta"], first["domain"]))
        self.assertNotIn(plan.name, (first["title"], first["meta"]))
        # Setup line keeps its kind with group + plan name.
        self.assertEqual(second["title"], plan.plan_name)
        self.assertEqual(second["meta"], f"Setup fee: {group.name} {plan.plan_name} x1")
        # Billing identity for pre-payment verification.
        billing = detail["customer"]
        self.assertTrue(billing["name"])
        self.assertEqual(billing["company"], "Acme Ltd")
        self.assertEqual(billing["tax_id"], "VAT123")
        self.assertIn("1 Main St", billing["address"])
        self.assertIn("Springfield", billing["address"])
        # Guest gets no invoice detail.
        frappe.set_user("Guest")
        self.assertRaises(frappe.PermissionError, apis.my_invoice_detail, inv.name)
