"""Live Plesk adapter (XML API over HTTPS, Basic auth).

Sandbox by default: credentials come from the Server row (api_username +
api_secret Password field). Packet shapes mirror Plesk's official api-php-lib
(webspace/add, set/status, del, get/dataset; customer/set; server/get_protos).
Nothing is contacted until a Server row holds real creds (manual gate).
"""

import time
import xml.etree.ElementTree as ET

import frappe

from lube_station.lube_station.adapters.utils import redact

from .base import ProvisioningAdapter

PORT = 8443
ENDPOINT = "/enterprise/control/agent.php"
TIMEOUT = 20
RETRIES = 3
STATUS_ACTIVE = "0"
STATUS_SUSPENDED = "16"


def _http_post(url, headers, body, timeout):
    import requests

    return requests.post(url, headers=headers, data=body.encode(), timeout=timeout)


def _build(operator, operation, filter_field=None, filter_value=None, values=None, extra=None):
    """Minimal packet: <packet><op><operation>[<filter/>][<values/>|...]"""
    packet = ET.Element("packet")
    op = ET.SubElement(packet, operator)
    node = ET.SubElement(op, operation)
    if filter_field is not None:
        filt = ET.SubElement(node, "filter")
        ET.SubElement(filt, filter_field).text = str(filter_value)
    if values:
        vals = ET.SubElement(node, "values")
        gen = ET.SubElement(vals, "gen_setup")
        for key, val in values.items():
            ET.SubElement(gen, key).text = str(val)
    if extra:
        for parent_tag, children in extra.items():
            parent = ET.SubElement(node, parent_tag)
            for child in children:
                if isinstance(child, dict):
                    tag = child.pop("_tag")
                    el = ET.SubElement(parent, tag)
                    for key, val in child.items():
                        ET.SubElement(el, key).text = str(val)
                else:
                    ET.SubElement(parent, child)
    return ET.tostring(packet, encoding="unicode")


class PleskAdapter(ProvisioningAdapter):
    adapter_name = "Plesk"

    # -- connection -----------------------------------------------------
    def _server(self, server):
        doc = frappe.get_doc("Server", server) if isinstance(server, str) else server
        host = (doc.ip_address or doc.hostname or "").strip()
        if not host:
            frappe.throw(f"Server {doc.name} has no hostname/IP")
        user = (doc.api_username or "").strip()
        token = doc.get_password(fieldname="api_secret", raise_exception=False)
        if not user or not token:
            frappe.throw(f"Server {doc.name} has no API credentials")
        return doc, host, user, token

    def _service(self, service):
        svc = frappe.get_doc("Service", service) if isinstance(service, str) else service
        if not svc.server:
            frappe.throw(f"Service {svc.name} has no server assigned")
        if not svc.svc_username:
            frappe.throw(f"Service {svc.name} has no account username")
        if not svc.primary_domain:
            frappe.throw(f"Service {svc.name} has no primary domain")
        return svc

    # -- transport ------------------------------------------------------
    def _call(self, server, operator, operation, payload, transport=None):
        import base64

        doc, host, user, token = self._server(server)
        transport = transport or _http_post
        url = f"https://{host}:{PORT}{ENDPOINT}"
        creds = base64.b64encode(f"{user}:{token}".encode()).decode()
        headers = {"Content-Type": "text/xml", "Authorization": f"Basic {creds}"}
        last_error = None
        for attempt in range(1, RETRIES + 1):
            try:
                resp = transport(url, headers, payload, TIMEOUT)
                return self._result(doc, operator, operation, resp)
            except frappe.ValidationError:
                raise
            except Exception as e:
                last_error = e
                time.sleep(min(2**attempt, 8))
        frappe.throw(f"Plesk {operator}/{operation} failed after {RETRIES} attempts: {last_error}")

    def _result(self, server_doc, operator, operation, resp):
        if getattr(resp, "status_code", 200) >= 500:
            raise ConnectionError(f"HTTP {resp.status_code}")
        try:
            root = ET.fromstring(resp.text if hasattr(resp, "text") else resp)
        except Exception:
            frappe.throw(f"Plesk {operator}/{operation} returned non-XML response")
        result = root.find(f"./{operator}/{operation}/result")
        if result is None:
            result = root.find(".//result")
        status = (result.findtext("status") if result is not None else "") or ""
        if status.strip() != "ok":
            err = (result.findtext("errtext") if result is not None else "") or "unknown error"
            frappe.throw(f"Plesk {operator}/{operation} rejected: {err}", frappe.ValidationError)
        return result

    # -- lifecycle ------------------------------------------------------
    def create_account(self, service, password=None, transport=None):
        import secrets

        svc = self._service(service)
        password = password or secrets.token_urlsafe(16)
        root = ET.Element("packet")
        add = ET.SubElement(ET.SubElement(root, "webspace"), "add")
        gen = ET.SubElement(add, "gen_setup")
        ET.SubElement(gen, "name").text = svc.primary_domain
        ET.SubElement(gen, "owner-login").text = svc.svc_username
        ET.SubElement(gen, "htype").text = "vrt_hst"
        hosting = ET.SubElement(add, "hosting")
        vrt = ET.SubElement(hosting, "vrt_hst")
        for prop, val in (("ftp_login", svc.svc_username), ("ftp_password", password)):
            p = ET.SubElement(vrt, "property")
            ET.SubElement(p, "name").text = prop
            ET.SubElement(p, "value").text = val
        plan = self._plan(svc)
        if plan:
            ET.SubElement(add, "plan-name").text = plan
        payload = ET.tostring(root, encoding="unicode")
        result = self._call(svc.server, "webspace", "add", payload, transport)
        return {"created": svc.svc_username, "password": password, "id": result.findtext("id")}

    def suspend_account(self, service, transport=None):
        svc = self._service(service)
        payload = _build("webspace", "set", "name", svc.primary_domain, {"status": STATUS_SUSPENDED})
        self._call(svc.server, "webspace", "set", payload, transport)
        return {"suspended": svc.svc_username}

    def unsuspend_account(self, service, transport=None):
        svc = self._service(service)
        payload = _build("webspace", "set", "name", svc.primary_domain, {"status": STATUS_ACTIVE})
        self._call(svc.server, "webspace", "set", payload, transport)
        return {"unsuspended": svc.svc_username}

    def terminate_account(self, service, transport=None):
        svc = self._service(service)
        payload = _build("webspace", "del", "name", svc.primary_domain)
        self._call(svc.server, "webspace", "del", payload, transport)
        return {"terminated": svc.svc_username}

    def change_password(self, service, password, transport=None):
        svc = self._service(service)
        payload = _build("customer", "set", "login", svc.svc_username, {"passwd": password})
        self._call(svc.server, "customer", "set", payload, transport)
        return {"changed": svc.svc_username}

    def change_package(self, service, new_plan, transport=None):
        frappe.throw("Plesk has no plan-switch API: recreate the subscription on the new plan")

    def get_usage(self, service, transport=None):
        svc = self._service(service)
        packet = ET.Element("packet")
        op = ET.SubElement(packet, "webspace")
        node = ET.SubElement(op, "get")
        filt = ET.SubElement(node, "filter")
        ET.SubElement(filt, "name").text = svc.primary_domain
        dataset = ET.SubElement(node, "dataset")
        ET.SubElement(dataset, "disk_usage")
        ET.SubElement(dataset, "stat")
        result = self._call(svc.server, "webspace", "get", ET.tostring(packet, encoding="unicode"), transport)
        return {"disk": self._number(result, ("disk_space", "diskspace")), "bandwidth": self._number(result, ("traffic", "bandwidth"))}

    def test_connection(self, server, transport=None):
        packet = ET.Element("packet")
        op = ET.SubElement(packet, "server")
        ET.SubElement(op, "get_protos")
        self._call(server, "server", "get_protos", ET.tostring(packet, encoding="unicode"), transport)
        doc = server if not isinstance(server, str) else frappe.get_doc("Server", server)
        return {"ok": True, "server": doc.name}

    # -- helpers ----------------------------------------------------------
    def create_sso_session(self, service, transport=None):
        """Plesk server/create_session -> one-time rsession URL."""
        svc = self._service(service)
        host = self._panel_host(svc)
        if not host:
            frappe.throw("Panel login failed, please try again later")
        packet = ET.Element("packet")
        op = ET.SubElement(packet, "server")
        node = ET.SubElement(op, "create_session")
        ET.SubElement(node, "login").text = svc.svc_username
        data = ET.SubElement(node, "data")
        ET.SubElement(data, "user_ip").text = ""
        ET.SubElement(data, "source_server").text = ""
        result = self._call(svc.server, "server", "create_session", ET.tostring(packet, encoding="unicode"), transport)
        session_id = (result.findtext("id") or result.findtext(".//id") or "").strip() if result is not None else ""
        if not session_id:
            frappe.throw("Panel login failed, please try again later")
        return {"url": f"https://{host}:8443/enterprise/rsession_init.php?PLESKSESSID={session_id}"}

    def _panel_host(self, svc):
        try:
            if not svc.server or not frappe.db.exists("Server", svc.server):
                return ""
            doc = frappe.get_doc("Server", svc.server)
            return (doc.ip_address or doc.hostname or "").strip()
        except Exception:
            return ""

    def get_client_area(self, service):
        svc = self._service(service)
        host = self._panel_host(svc)
        if not host:
            return {"panels": [], "buttons": []}
        return {
            "panels": [],
            "buttons": [
                {"key": "panel", "label": "Open Plesk", "kind": "link", "url": f"https://{host}:8443"},
            ],
        }

    def _plan(self, svc):
        try:
            plan = frappe.get_doc("Hosting Plan", svc.hosting_plan) if svc.hosting_plan else None
            return (plan.plan_name if plan else "") or ""
        except Exception:
            return ""

    def _number(self, result, tags):
        for tag in tags:
            el = result.find(f".//{tag}")
            if el is not None and (el.text or "").strip().isdigit():
                return int(el.text.strip())
        return 0
