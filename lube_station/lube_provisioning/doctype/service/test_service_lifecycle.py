import uuid

import frappe
from frappe.tests import IntegrationTestCase


def _unique_customer():
    email = f"svc-{uuid.uuid4().hex[:8]}@test.com"
    user = frappe.get_doc({"doctype": "User", "email": email, "first_name": "Svc", "enabled": 1}).insert(ignore_permissions=True)
    return frappe.get_doc({"doctype": "Hosting Customer", "user": user.name, "status": "Active"}).insert()


class TestServiceLifecycle(IntegrationTestCase):
    def test_create_from_order_assigns_server_and_username(self):
        import json

        from lube_station.lube_provisioning.doctype.service.service import create_from_order

        cust = _unique_customer()
        server = frappe.get_doc(
            {"doctype": "Server", "hostname": f"assign-{uuid.uuid4().hex[:6]}.test", "ip_address": "203.0.113.50", "control_panel": "cPanel / WHM", "status": "Active"}
        ).insert()
        group = frappe.get_doc({"doctype": "Server Group", "group_name": f"ASG {uuid.uuid4().hex[:6]}", "fill_strategy": "Manual"}).insert()
        group.append("servers", {"server": server.name})
        group.save(ignore_permissions=True)
        pgroup = frappe.get_doc({"doctype": "Product Group", "group_name": f"AG {uuid.uuid4().hex[:6]}"}).insert()
        plan = frappe.get_doc(
            {"doctype": "Hosting Plan", "plan_name": f"AP {uuid.uuid4().hex[:6]}", "product_group": pgroup.name, "product_type": "Shared Hosting", "is_active": 1, "server_group": group.name}
        ).insert()
        frappe.get_doc({"doctype": "Plan Pricing", "hosting_plan": plan.name, "billing_cycle": "Monthly", "recurring_amount": 10}).insert()
        order = frappe.get_doc(
            {
                "doctype": "Order",
                "customer": cust.name,
                "status": "Accepted",
                "items": [
                    {
                        "item_type": "Hosting Plan",
                        "reference": plan.name,
                        "billing_cycle": "Monthly",
                        "unit_price": 10,
                        "quantity": 1,
                        "configuration_snapshot": json.dumps({"_domain": "mytestdomain.com"}),
                    }
                ],
            }
        ).insert(ignore_permissions=True)
        svc_name = create_from_order(order.name)["services"][0]
        self.assertEqual(frappe.db.get_value("Service", svc_name, "server"), server.name)
        self.assertEqual(frappe.db.get_value("Service", svc_name, "svc_username"), "mytestdo")

    def test_service_lifecycle(self):
        cust = _unique_customer()
        group = frappe.get_doc({"doctype": "Product Group", "group_name": f"Svc Group {uuid.uuid4().hex[:6]}"}).insert()
        plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": f"Svc Plan {uuid.uuid4().hex[:6]}", "product_group": group.name, "product_type": "Shared Hosting", "is_active": 1}).insert()
        svc = frappe.get_doc({"doctype": "Service", "customer": cust.name, "hosting_plan": plan.name, "status": "Pending", "recurring_amount": 10}).insert()
        svc.activate()
        self.assertEqual(frappe.db.get_value("Service", svc.name, "status"), "Active")
        svc.suspend("test")
        self.assertEqual(frappe.db.get_value("Service", svc.name, "status"), "Suspended")
        svc.unsuspend()
        self.assertEqual(frappe.db.get_value("Service", svc.name, "status"), "Active")
        self.assertRaises(frappe.ValidationError, svc.terminate, None)
        svc.terminate("customer cancelled, approved")
        self.assertEqual(frappe.db.get_value("Service", svc.name, "status"), "Terminated")

    def test_addon_cascade(self):
        """WHMCS add-on link: suspend/terminate follow parent, never auto-unsuspend."""
        from lube_station.lube_customers.doctype.order.order import place_order
        from lube_station.lube_provisioning.doctype.service.service import create_from_order

        cust = _unique_customer()
        group = frappe.get_doc({"doctype": "Product Group", "group_name": f"Addon Group {uuid.uuid4().hex[:6]}"}).insert()
        parent_plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": f"Addon Parent {uuid.uuid4().hex[:6]}", "product_group": group.name, "product_type": "Shared Hosting", "is_active": 1}).insert()
        addon_plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": f"Addon Child {uuid.uuid4().hex[:6]}", "product_group": group.name, "product_type": "SSL", "is_active": 1}).insert()
        for plan in (parent_plan, addon_plan):
            frappe.get_doc({"doctype": "Plan Pricing", "hosting_plan": plan.name, "billing_cycle": "Monthly", "recurring_amount": 10}).insert()
        parent = frappe.get_doc({"doctype": "Service", "customer": cust.name, "hosting_plan": parent_plan.name, "status": "Active", "recurring_amount": 10}).insert()
        cart = frappe.get_doc({"doctype": "Cart", "customer": cust.name}).insert(ignore_permissions=True)
        cart.append("items", {"item_type": "Hosting Plan", "hosting_plan": addon_plan.name, "billing_cycle": "Monthly", "quantity": 1, "parent_service": parent.name})
        cart.save(ignore_permissions=True)
        order_name = place_order(cart.name, cust.name)["order"]
        addon_name = create_from_order(order_name)["services"][0]
        self.assertEqual(frappe.db.get_value("Service", addon_name, "parent_service"), parent.name)
        frappe.get_doc("Service", addon_name).activate()
        frappe.get_doc("Service", parent.name).suspend("overdue test")
        self.assertEqual(frappe.db.get_value("Service", addon_name, "status"), "Suspended")
        frappe.get_doc("Service", parent.name).unsuspend()
        # No auto-unsuspend: add-on stays Suspended until its own payment.
        self.assertEqual(frappe.db.get_value("Service", addon_name, "status"), "Suspended")
        frappe.get_doc("Service", addon_name).unsuspend()
        frappe.get_doc("Service", parent.name).terminate("parent closed, approved")
        self.assertEqual(frappe.db.get_value("Service", addon_name, "status"), "Terminated")
