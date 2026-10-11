import frappe

from lube_station.lube_station.tests.helpers import make_customer, make_user
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.support import tickets


class TestHelpdeskLink(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        if not frappe.db.exists("DocType", "HD Ticket"):
            self.skipTest("HD Ticket (helpdesk app) not installed")

    def tearDown(self):
        frappe.set_user("Administrator")
        super().tearDown()

    def test_helpdesk_link(self):
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": make_user(__name__.split(".")[-1]), "status": "Active"}).insert()
        group = frappe.get_doc({"doctype": "Product Group", "group_name": "Sup Group"}).insert()
        plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": "Dedi Plan", "product_group": group.name, "product_type": "Dedicated Server", "is_active": 1}).insert()
        svc = frappe.get_doc({"doctype": "Service", "customer": cust.name, "hosting_plan": plan.name, "status": "Active", "recurring_amount": 500}).insert()
        out = tickets.create_ticket("Server down", "Need help", customer=cust.name, service=svc.name)
        self.assertEqual(out["priority"], "Urgent")
        self.assertTrue(frappe.db.exists("Ticket Hosting Reference", {"ticket": out["ticket"], "service": svc.name}))

    def test_create_ticket_sets_portal_identity(self):
        user = make_user("portalid")
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": user, "status": "Active"}).insert()
        out = tickets.create_ticket("Portal visible?", "body", customer=cust.name)
        doc = frappe.db.get_value(
            "HD Ticket", out["ticket"], ["raised_by", "via_customer_portal"], as_dict=True
        )
        self.assertEqual(doc["raised_by"], user)
        self.assertEqual(doc["via_customer_portal"], 1)

    def test_my_tickets_detail_reply(self):
        user = make_user("mytix")
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": user, "status": "Active"}).insert()
        out = tickets.create_ticket("List me", "body here", customer=cust.name)
        frappe.set_user(user)
        rows = tickets.my_tickets()
        self.assertTrue(any(r["name"] == out["ticket"] for r in rows))
        row = next(r for r in rows if r["name"] == out["ticket"])
        self.assertEqual(row["subject"], "List me")
        detail = tickets.my_ticket_detail(out["ticket"])
        self.assertEqual(detail["ticket"]["name"], out["ticket"])
        self.assertIn("comments", detail)
        self.assertIn("communications", detail)
        res = tickets.add_ticket_reply(out["ticket"], "Customer follow-up")
        self.assertTrue(res["replied"])
        detail2 = tickets.my_ticket_detail(out["ticket"])
        bodies = [c.get("content") or "" for c in detail2["communications"]]
        self.assertTrue(any("Customer follow-up" in b for b in bodies))

    def test_ticket_guards(self):
        user_a = make_user("guarda")
        cust_a = frappe.get_doc({"doctype": "Hosting Customer", "user": user_a, "status": "Active"}).insert()
        out = tickets.create_ticket("Guarded", "body", customer=cust_a.name)
        user_b = make_user("guardb")
        frappe.get_doc({"doctype": "Hosting Customer", "user": user_b, "status": "Active"}).insert()
        frappe.set_user(user_b)
        self.assertRaises(frappe.PermissionError, tickets.my_ticket_detail, out["ticket"])
        self.assertRaises(frappe.PermissionError, tickets.add_ticket_reply, out["ticket"], "hi")
        self.assertFalse(any(r["name"] == out["ticket"] for r in tickets.my_tickets()))
        frappe.set_user("Guest")
        self.assertRaises(frappe.PermissionError, tickets.my_tickets)
        frappe.set_user(user_a)
        self.assertRaises(frappe.ValidationError, tickets.add_ticket_reply, out["ticket"], "   ")
