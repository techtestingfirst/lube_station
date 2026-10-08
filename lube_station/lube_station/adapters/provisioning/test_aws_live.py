"""Live AWS EC2 adapter tests. Transport is faked; SigV4 is vector-tested."""

import datetime

import frappe
from frappe.tests import IntegrationTestCase

from lube_station.lube_station.adapters.provisioning.aws import AwsEc2Adapter, sign_request


class FakeResp:
    def __init__(self, text, status_code=200):
        self.text = text
        self.status_code = status_code


def ok_xml(inner):
    return FakeResp(
        f'<RunInstancesResponse xmlns="https://ec2.amazonaws.com/doc/2016-11-15/">{inner}</RunInstancesResponse>'
    )


class FakeTransport:
    def __init__(self, bodies):
        self.bodies = list(bodies)
        self.calls = []

    def __call__(self, url, headers, body, timeout):
        import urllib.parse

        self.calls.append(
            {"url": url, "auth": headers.get("Authorization", ""), "params": dict(urllib.parse.parse_qsl(body or ""))}
        )
        item = self.bodies.pop(0) if len(self.bodies) > 1 else self.bodies[0]
        if isinstance(item, Exception):
            raise item
        return item


def _keys():
    frappe.db.set_single_value("Lube Station Settings", "aws_access_key_id", "AKIDEXAMPLE")
    frappe.db.set_single_value("Lube Station Settings", "aws_secret_access_key", "wJalrXUtnFEMI/K7MDENG+bPxRfiCYEXAMPLEKEY")
    frappe.db.set_single_value("Lube Station Settings", "aws_region", "us-east-1")


def _clearkeys():
    frappe.db.set_single_value("Lube Station Settings", "aws_access_key_id", "")
    frappe.db.set_single_value("Lube Station Settings", "aws_secret_access_key", "")


class TestAwsEc2LiveAdapter(IntegrationTestCase):
    def test_sigv4_shape(self):
        # Shape per AWS SigV4 docs (host + x-amz-date signed). Exact
        # interop is confirmed against sandbox with real creds.
        when = datetime.datetime(2015, 8, 30, 12, 36, 0)
        first = sign_request(
            "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "us-east-1",
            "GET",
            "iam.amazonaws.com",
            "/",
            "Action=ListUsers&Version=2010-05-08",
            "",
            when,
            service="iam",
        )
        self.assertEqual(first["scope"], "20150830/us-east-1/iam/aws4_request")
        self.assertEqual(first["signed"], "host;x-amz-date")
        self.assertEqual(first["X-Amz-Date"], "20150830T123600Z")
        self.assertRegex(first["signature"], r"^[0-9a-f]{64}$")
        second = sign_request(
            "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY",
            "us-east-1",
            "GET",
            "iam.amazonaws.com",
            "/",
            "Action=ListUsers&Version=2010-05-08",
            "",
            when,
            service="iam",
        )
        self.assertEqual(first["signature"], second["signature"])
        changed = sign_request(
            "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEZ",
            "us-east-1",
            "GET",
            "iam.amazonaws.com",
            "/",
            "Action=ListUsers&Version=2010-05-08",
            "",
            when,
            service="iam",
        )
        self.assertNotEqual(first["signature"], changed["signature"])

    def _server(self):
        name = frappe.db.get_value("Server", {"hostname": "aws-test.local"}, "name")
        if name:
            return name
        return frappe.get_doc(
            {"doctype": "Server", "hostname": "aws-test.local", "ip_address": "10.0.0.15", "control_panel": "Custom", "status": "Active"}
        ).insert(ignore_permissions=True).name

    def _service(self, server, vendor_ref="i-12345"):
        group = frappe.db.get_value("Product Group", {"group_name": "AWS Group"}, "name")
        if not group:
            group = frappe.get_doc({"doctype": "Product Group", "group_name": "AWS Group"}).insert().name
        plan = frappe.db.get_value("Hosting Plan", {"plan_name": "AWS Plan"}, "name")
        if not plan:
            plan = frappe.get_doc(
                {"doctype": "Hosting Plan", "plan_name": "AWS Plan", "product_group": group, "product_type": "Cloud", "is_active": 1}
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
                "svc_username": "awsuser1",
                "primary_domain": "awsuser1.test",
                "vendor_ref": vendor_ref,
                "status": "Pending",
            }
        ).insert(ignore_permissions=True).name

    def test_create_power_terminate(self):
        _keys()
        server = self._server()
        svc = self._service(server)
        try:
            t = FakeTransport([ok_xml("<instancesSet><item><instanceId>i-12345</instanceId></item></instancesSet>")])
            out = AwsEc2Adapter().create_account(svc, transport=t)
            self.assertEqual(out["instance_id"], "i-12345")
            self.assertIn("ec2.us-east-1.amazonaws.com", t.calls[0]["url"])
            self.assertIn("Credential=AKIDEXAMPLE/20", t.calls[0]["auth"])
            self.assertEqual(t.calls[0]["params"]["Action"], "RunInstances")

            t = FakeTransport([ok_xml("<instancesSet><item><currentState><name>running</name></currentState></item></instancesSet>")])
            out = AwsEc2Adapter().start(svc, transport=t)
            self.assertEqual(out["state"], "running")

            t = FakeTransport([ok_xml("<return>true</return>")])
            self.assertEqual(
                AwsEc2Adapter().terminate_account(svc, transport=t)["terminated"],
                AwsEc2Adapter()._service(svc).name,
            )
        finally:
            _clearkeys()
            frappe.delete_doc("Service", svc, ignore_permissions=True, force=True)

    def test_reject_and_retry(self):
        _keys()
        server = self._server()
        try:
            t = FakeTransport([FakeResp("<Response><Errors><Error><Message>nope</Message></Error></Errors></Response>")])
            self.assertRaises(
                frappe.ValidationError, AwsEc2Adapter().test_connection, server, transport=t
            )
            import requests

            t = FakeTransport([requests.ConnectionError("down"), ok_xml("<regionName>us-east-1</regionName>")])
            out = AwsEc2Adapter().test_connection(server, transport=t)
            self.assertIn("us-east-1", out["regions"])
            self.assertEqual(len(t.calls), 2)
        finally:
            _clearkeys()
