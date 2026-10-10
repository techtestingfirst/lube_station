import frappe
from frappe.tests import IntegrationTestCase


class TestServerConnection(IntegrationTestCase):
    def _make_server(self, hostname):
        name = frappe.db.get_value("Server", {"hostname": hostname}, "name")
        if name:
            return frappe.get_doc("Server", name)
        doc = frappe.get_doc(
            {
                "doctype": "Server",
                "hostname": hostname,
                "ip_address": "10.0.0.99",
                "api_username": "root",
                "control_panel": "cPanel / WHM",
                "status": "Active",
            }
        ).insert(ignore_permissions=True)
        doc.set("api_secret", "tok123")
        doc.save(ignore_permissions=True)
        return doc

    def test_online_path_stores_status(self):
        from lube_station.lube_provisioning.doctype.server import server as server_mod

        srv = self._make_server("conn-ok.local")

        class FakeAdapter:
            def test_connection(self, name):
                return {"ok": True, "server": name}

        orig = server_mod._load_adapter
        server_mod._load_adapter = lambda panel: FakeAdapter()
        try:
            out = frappe.get_doc("Server", srv.name).test_connection()
            self.assertTrue(out["ok"])
            self.assertEqual(out["status"], "Online")
            fresh = frappe.get_doc("Server", srv.name)
            self.assertEqual(fresh.connection_status, "Online")
            self.assertTrue(fresh.last_checked_on)
        finally:
            server_mod._load_adapter = orig
            frappe.delete_doc("Server", srv.name, ignore_permissions=True, force=True)

    def test_failed_path_stores_message(self):
        from lube_station.lube_provisioning.doctype.server import server as server_mod

        srv = self._make_server("conn-fail.local")

        class BoomAdapter:
            def test_connection(self, name):
                raise ConnectionError("down")

        orig = server_mod._load_adapter
        server_mod._load_adapter = lambda panel: BoomAdapter()
        try:
            out = frappe.get_doc("Server", srv.name).test_connection()
            self.assertFalse(out["ok"])
            self.assertEqual(out["status"], "Failed")
            fresh = frappe.get_doc("Server", srv.name)
            self.assertEqual(fresh.connection_status, "Failed")
            self.assertIn("down", fresh.last_check_message)
        finally:
            server_mod._load_adapter = orig
            frappe.delete_doc("Server", srv.name, ignore_permissions=True, force=True)

    def test_unknown_panel_fails_cleanly(self):
        srv = self._make_server("conn-custom.local")
        srv.control_panel = "Custom"
        srv.save(ignore_permissions=True)
        try:
            out = frappe.get_doc("Server", srv.name).test_connection()
            self.assertFalse(out["ok"])
            self.assertEqual(out["status"], "Failed")
        finally:
            frappe.delete_doc("Server", srv.name, ignore_permissions=True, force=True)
