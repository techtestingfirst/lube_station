"""Live Plesk adapter tests. Transport is faked; no network happens."""

import xml.etree.ElementTree as ET

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.provisioning.plesk import PleskAdapter


class FakeResp:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code


def ok(extra=""):
    return FakeResp(f"<packet><webspace><add><result><status>ok</status>{extra}</result></add></webspace></packet>")


def ok_op(operator, operation, extra=""):
    return FakeResp(
        f"<packet><{operator}><{operation}><result><status>ok</status>{extra}</result></{operation}></{operator}></packet>"
    )


def err(operator, operation, text="bad"):
    return FakeResp(
        f"<packet><{operator}><{operation}><result><status>error</status><errtext>{text}</errtext></result></{operation}></{operator}></packet>"
    )


class FakeTransport:
    def __init__(self, bodies):
        self.bodies = list(bodies)
        self.calls = []

    def __call__(self, url, headers, body, timeout):
        self.calls.append({"url": url, "auth": headers.get("Authorization", ""), "body": body})
        item = self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]
        if isinstance(item, Exception):
            raise item
        return item


class TestPleskLiveAdapter(IntegrationTestCase):
    def _server(self):
        name = frappe.db.get_value("Server", {"hostname": "plesk-test.local"}, "name")
        if name:
            return name
        doc = frappe.get_doc(
            {
                "doctype": "Server",
                "hostname": "plesk-test.local",
                "ip_address": "10.0.0.10",
                "api_username": "admin",
                "control_panel": "Plesk",
                "status": "Active",
            }
        ).insert(ignore_permissions=True)
        doc.set("api_secret", "sek123")
        doc.save(ignore_permissions=True)
        return doc.name

    def _service(self, server):
        group = frappe.db.get_value("Product Group", {"group_name": "Plesk Group"}, "name")
        if not group:
            group = frappe.get_doc({"doctype": "Product Group", "group_name": "Plesk Group"}).insert().name
        plan = frappe.db.get_value("Hosting Plan", {"plan_name": "Plesk Plan"}, "name")
        if not plan:
            plan = frappe.get_doc(
                {
                    "doctype": "Hosting Plan",
                    "plan_name": "Plesk Plan",
                    "product_group": group,
                    "product_type": "Shared Hosting",
                    "is_active": 1,
                }
            ).insert().name
        cust = frappe.db.get_value("Hosting Customer", {"user": "Administrator"}, "name")
        if not cust:
            cust = frappe.get_doc({"doctype": "Hosting Customer", "user": "Administrator", "status": "Active"}).insert().name
        return frappe.get_doc(
            {
                "doctype": "Service",
                "customer": cust,
                "hosting_plan": plan,
                "server": server,
                "svc_username": "pleskuser1",
                "primary_domain": "pleskuser1.test",
                "status": "Pending",
            }
        ).insert(ignore_permissions=True).name

    def _xml(self, call):
        return ET.fromstring(call["body"])

    def test_create_suspend_terminate(self):
        server = self._server()
        svc = self._service(server)
        try:
            t = FakeTransport([ok("<id>7</id>")])
            out = PleskAdapter().create_account(svc, password="Pw12345678!", transport=t)
            self.assertEqual(out["id"], "7")
            root = self._xml(t.calls[0])
            self.assertEqual(root.findtext("./webspace/add/gen_setup/name"), "pleskuser1.test")
            self.assertEqual(root.findtext("./webspace/add/gen_setup/owner-login"), "pleskuser1")
            self.assertTrue(t.calls[0]["url"].endswith(":8443/enterprise/control/agent.php"))
            self.assertTrue(t.calls[0]["auth"].startswith("Basic "))

            t = FakeTransport([ok_op("webspace", "set")])
            PleskAdapter().suspend_account(svc, transport=t)
            root = self._xml(t.calls[0])
            self.assertEqual(root.findtext("./webspace/set/values/gen_setup/status"), "16")

            t = FakeTransport([ok_op("webspace", "set")])
            PleskAdapter().unsuspend_account(svc, transport=t)
            root = self._xml(t.calls[0])
            self.assertEqual(root.findtext("./webspace/set/values/gen_setup/status"), "0")

            t = FakeTransport([ok_op("webspace", "del")])
            self.assertEqual(
                PleskAdapter().terminate_account(svc, transport=t)["terminated"], "pleskuser1"
            )
        finally:
            frappe.delete_doc("Service", svc, ignore_permissions=True, force=True)

    def test_reject_and_retry(self):
        server = self._server()
        t = FakeTransport([err("server", "get_protos", "denied")])
        self.assertRaises(
            frappe.ValidationError, PleskAdapter().test_connection, server, transport=t
        )
        import requests

        t = FakeTransport([requests.ConnectionError("down"), ok_op("server", "get_protos")])
        self.assertTrue(PleskAdapter().test_connection(server, transport=t)["ok"])
        self.assertEqual(len(t.calls), 2)

    def test_usage_and_plan_switch(self):
        server = self._server()
        svc = self._service(server)
        try:
            body = ok_op("webspace", "get", "<data><disk_usage><disk_space>1024</disk_space></disk_usage><stat><traffic>2048</traffic></stat></data>")
            t = FakeTransport([body])
            out = PleskAdapter().get_usage(svc, transport=t)
            self.assertEqual(out, {"disk": 1024, "bandwidth": 2048})
            self.assertRaises(Exception, PleskAdapter().change_package, svc, "X", transport=t)
        finally:
            frappe.delete_doc("Service", svc, ignore_permissions=True, force=True)

    def test_create_sso_session(self):
        server = self._server()
        svc = self._service(server)
        try:
            t = FakeTransport([ok_op("server", "create_session", "<id>sess-123</id>")])
            out = PleskAdapter().create_sso_session(svc, transport=t)
            self.assertIn("PLESKSESSID=sess-123", out["url"])
            self.assertIn("create_session", t.calls[0]["body"])
        finally:
            frappe.delete_doc("Service", svc, ignore_permissions=True, force=True)
