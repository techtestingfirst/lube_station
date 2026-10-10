import uuid

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_domains.doctype.registered_domain.registered_domain import subdomain_suffixes, validate_subdomain


def _portal_customer():
    from lube_station.lube_station.portal import apis

    email = f"sub-{uuid.uuid4().hex[:8]}@test.com"
    user = frappe.get_doc({"doctype": "User", "email": email, "first_name": "Sub", "enabled": 1}).insert(ignore_permissions=True)
    cust = frappe.get_doc({"doctype": "Hosting Customer", "user": user.name, "status": "Active"}).insert()
    frappe.set_user(user.name)
    return apis, cust


class TestSubdomain(IntegrationTestCase):
    def tearDown(self):
        frappe.set_user("Administrator")
        frappe.db.set_single_value("Lube Station Settings", "free_subdomain_suffixes", "")
        super().tearDown()

    def test_disabled_by_default(self):
        self.assertEqual(subdomain_suffixes(), [])
        self.assertRaises(frappe.ValidationError, validate_subdomain, "a.cust.test")

    def test_validation(self):
        frappe.db.set_single_value("Lube Station Settings", "free_subdomain_suffixes", "cust.test")
        self.assertEqual(validate_subdomain("My-Site.cust.test"), "my-site.cust.test")
        for bad in ("-a.cust.test", "a-.cust.test", "a!.cust.test", "cust.test", "a.other.test", ""):
            with self.assertRaises(frappe.ValidationError, msg=f"accepted {bad!r}"):
                validate_subdomain(bad)

    def test_taken(self):
        frappe.db.set_single_value("Lube Station Settings", "free_subdomain_suffixes", "cust.test")
        email = f"taken-{uuid.uuid4().hex[:8]}@test.com"
        user = frappe.get_doc({"doctype": "User", "email": email, "first_name": "Taken", "enabled": 1}).insert(ignore_permissions=True)
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": user.name, "status": "Active"}).insert()
        group = frappe.get_doc({"doctype": "Product Group", "group_name": f"Taken Group {uuid.uuid4().hex[:6]}"}).insert()
        plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": f"Taken Plan {uuid.uuid4().hex[:6]}", "product_group": group.name, "product_type": "Shared Hosting", "is_active": 1}).insert()
        frappe.get_doc({"doctype": "Service", "customer": cust.name, "hosting_plan": plan.name, "status": "Active", "primary_domain": "gone.cust.test", "recurring_amount": 5}).insert()
        self.assertRaises(frappe.ValidationError, validate_subdomain, "gone.cust.test")
        frappe.get_doc({"doctype": "Registered Domain", "domain_name": "reg.cust.test", "customer": cust.name, "status": "Registered"}).insert(ignore_permissions=True)
        self.assertRaises(frappe.ValidationError, validate_subdomain, "reg.cust.test")

    def test_subdomain_order_flow(self):
        from lube_station.lube_customers.doctype.order.order import place_order
        from lube_station.lube_provisioning.doctype.service.service import create_from_order

        frappe.db.set_single_value("Lube Station Settings", "free_subdomain_suffixes", "cust.test")
        group = frappe.get_doc({"doctype": "Product Group", "group_name": f"Sub Group {uuid.uuid4().hex[:6]}"}).insert()
        schema = frappe.get_doc(
            {
                "doctype": "Product Type Schema",
                "schema_name": f"Sub Schema {uuid.uuid4().hex[:6]}",
                "product_type": "Shared Hosting",
                "requires_domain": 1,
            }
        ).insert()
        plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": f"Sub Plan {uuid.uuid4().hex[:6]}", "product_group": group.name, "product_type": "Shared Hosting", "product_type_schema": schema.name, "is_active": 1}).insert()
        frappe.get_doc({"doctype": "Plan Pricing", "hosting_plan": plan.name, "billing_cycle": "Monthly", "recurring_amount": 5}).insert()
        apis, cust = _portal_customer()
        cart = frappe.get_doc({"doctype": "Cart", "customer": cust.name}).insert(ignore_permissions=True)
        cart.append("items", {"item_type": "Hosting Plan", "hosting_plan": plan.name, "billing_cycle": "Monthly", "quantity": 1})
        cart.save(ignore_permissions=True)
        row = frappe.get_doc("Cart", cart.name).items[0].name
        name = f"site-{uuid.uuid4().hex[:6]}.cust.test"
        view = apis.cart_set_domain(cart.name, row, name, "subdomain")
        self.assertEqual(view["items"][0]["domain"], name)
        # requires_domain satisfied by the subdomain; service named for provisioning.
        order_name = place_order(cart.name, cust.name)["order"]
        svc_name = create_from_order(order_name)["services"][0]
        self.assertEqual(frappe.db.get_value("Service", svc_name, "primary_domain"), name)

    def test_attached_domain_names_service(self):
        from lube_station.lube_customers.doctype.order.order import place_order
        from lube_station.lube_provisioning.doctype.service.service import create_from_order

        group = frappe.get_doc({"doctype": "Product Group", "group_name": f"Own Group {uuid.uuid4().hex[:6]}"}).insert()
        plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": f"Own Plan {uuid.uuid4().hex[:6]}", "product_group": group.name, "product_type": "Shared Hosting", "is_active": 1}).insert()
        frappe.get_doc({"doctype": "Plan Pricing", "hosting_plan": plan.name, "billing_cycle": "Monthly", "recurring_amount": 5}).insert()
        apis, cust = _portal_customer()
        cart = frappe.get_doc({"doctype": "Cart", "customer": cust.name}).insert(ignore_permissions=True)
        cart.append("items", {"item_type": "Hosting Plan", "hosting_plan": plan.name, "billing_cycle": "Monthly", "quantity": 1})
        cart.save(ignore_permissions=True)
        row = frappe.get_doc("Cart", cart.name).items[0].name
        apis.cart_set_domain(cart.name, row, f"mysite-{uuid.uuid4().hex[:6]}.com", "own")
        order_name = place_order(cart.name, cust.name)["order"]
        svc_name = create_from_order(order_name)["services"][0]
        self.assertTrue(frappe.db.get_value("Service", svc_name, "primary_domain").endswith(".com"))

    def test_subdomain_rejected_as_domain_line(self):
        apis, cust = _portal_customer()
        cart = frappe.get_doc({"doctype": "Cart", "customer": cust.name}).insert(ignore_permissions=True)
        with self.assertRaises(frappe.ValidationError) as ctx:
            apis.cart_add_domain(cart.name, "a.cust.test", "subdomain", 1)
        self.assertIn("attach to a hosting plan", str(ctx.exception))

    def test_domain_deferred_to_step_two(self):
        """Step 1 (configure) must not demand the domain picked in step 2."""
        from lube_station.lube_customers.doctype.order.order import place_order

        group = frappe.get_doc({"doctype": "Product Group", "group_name": f"Defer Group {uuid.uuid4().hex[:6]}"}).insert()
        schema = frappe.get_doc(
            {
                "doctype": "Product Type Schema",
                "schema_name": f"Defer Schema {uuid.uuid4().hex[:6]}",
                "product_type": "Shared Hosting",
                "requires_domain": 1,
            }
        ).insert()
        plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": f"Defer Plan {uuid.uuid4().hex[:6]}", "product_group": group.name, "product_type": "Shared Hosting", "product_type_schema": schema.name, "is_active": 1}).insert()
        frappe.get_doc({"doctype": "Plan Pricing", "hosting_plan": plan.name, "billing_cycle": "Monthly", "recurring_amount": 5}).insert()
        apis, cust = _portal_customer()
        view = apis.cart_add(hosting_plan=plan.name, billing_cycle="Monthly", configuration={})
        self.assertTrue(view["items"])
        cart_name = view["cart"]
        # ...but ordering without any domain still fails.
        self.assertRaises(frappe.ValidationError, place_order, cart_name, cust.name)
