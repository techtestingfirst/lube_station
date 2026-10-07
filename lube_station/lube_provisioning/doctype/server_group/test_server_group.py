import frappe
from frappe.tests import IntegrationTestCase


class TestServerGroup(IntegrationTestCase):
    def test_server_group(self):
        sg = frappe.get_doc({"doctype": "Server Group", "group_name": "SG-Test", "fill_strategy": "Manual"}).insert()
        s = frappe.get_doc({"doctype": "Server", "hostname": "srv1.test", "server_group": sg.name}).insert()
        sg.append("servers", {"server": s.name})
        sg.save()
        self.assertEqual(sg.pick_server(), s.name)
