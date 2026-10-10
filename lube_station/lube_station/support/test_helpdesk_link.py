import frappe

from lube_station.lube_station.tests.helpers import make_customer, make_user
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.support.tickets import create_ticket


class TestHelpdeskLink(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        if not frappe.db.exists("DocType", "HD Ticket"):
            self.skipTest("HD Ticket (helpdesk app) not installed")

    def test_helpdesk_link(self):
        cust = frappe.get_doc({"doctype": "Hosting Customer", "user": make_user(__name__.split(".")[-1]), "status": "Active"}).insert()
        group = frappe.get_doc({"doctype": "Product Group", "group_name": "Sup Group"}).insert()
        plan = frappe.get_doc({"doctype": "Hosting Plan", "plan_name": "Dedi Plan", "product_group": group.name, "product_type": "Dedicated Server", "is_active": 1}).insert()
        svc = frappe.get_doc({"doctype": "Service", "customer": cust.name, "hosting_plan": plan.name, "status": "Active", "recurring_amount": 500}).insert()
        out = create_ticket("Server down", "Need help", customer=cust.name, service=svc.name)
        self.assertEqual(out["priority"], "Urgent")
        self.assertTrue(frappe.db.exists("Ticket Hosting Reference", {"ticket": out["ticket"], "service": svc.name}))
