"""Live cPanel/WHM adapter (WHM API v1 over HTTPS).

Sandbox by default: server credentials come from the Server record
(api_username + api_secret Password field). Nothing is contacted until a
Server row holds real creds (manual gate). HTTP is injectable so tests never
touch the network; every call is audit-logged redacted to Provider API Log.
"""

import time

import frappe

from lube_station.lube_station.adapters.utils import redact

from .base import ProvisioningAdapter

PORT = 2087
TIMEOUT = 20
RETRIES = 3


def _http_get(url, headers, params, timeout):
    import requests

    return requests.get(url, headers=headers, params=params, timeout=timeout, verify=True)


class CpanelWhmAdapter(ProvisioningAdapter):
    adapter_name = "cPanel / WHM"

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
        return svc

    # -- transport ------------------------------------------------------
    def _call(self, server, func, params, transport=None):
        doc, host, user, token = self._server(server)
        transport = transport or _http_get
        url = f"https://{host}:{PORT}/json-api/{func}"
        headers = {"Authorization": f"whm {user}:{token}"}
        safe = redact(dict(params or {}))
        last_error = None
        for attempt in range(1, RETRIES + 1):
            try:
                resp = transport(url, headers, dict(params or {}), TIMEOUT)
                return self._result(doc, func, safe, resp)
            except frappe.ValidationError:
                raise
            except Exception as e:
                last_error = e
                self._audit(doc, func, safe, "Retry", str(e)[:500])
                time.sleep(min(2**attempt, 8))
        self._audit(doc, func, safe, "Failed", str(last_error)[:500])
        frappe.throw(f"WHM {func} failed after {RETRIES} attempts: {last_error}")

    def _result(self, server_doc, func, safe_params, resp):
        if getattr(resp, "status_code", 200) >= 500:
            raise ConnectionError(f"HTTP {resp.status_code}")
        try:
            body = resp.json()
        except Exception:
            frappe.throw(f"WHM {func} returned non-JSON response")
        data = body.get("data", body) if isinstance(body, dict) else {}
        meta = (body.get("metadata") or {}) if isinstance(body, dict) else {}
        if meta.get("result") == 0:
            reason = meta.get("reason", "unknown error")
            self._audit(server_doc, func, safe_params, "Failed", reason[:500])
            frappe.throw(f"WHM {func} rejected: {reason}", frappe.ValidationError)
        self._audit(server_doc, func, safe_params, "Success", "")
        return data if isinstance(data, dict) else {"result": data}

    def _audit(self, server_doc, func, safe_params, status, error_text):
        try:
            provider = frappe.db.get_value("Infrastructure Provider", {"status": "Active"}, "name")
            if not provider or not frappe.db.exists("DocType", "Provider API Log"):
                return
            frappe.get_doc(
                {
                    "doctype": "Provider API Log",
                    "provider": provider,
                    "action": f"cpanel:{func}:{redact(safe_params).get('user', '')}",
                    "status": status,
                    "error_text": error_text,
                }
            ).insert(ignore_permissions=True)
        except Exception:
            pass

    # -- lifecycle ------------------------------------------------------
    def create_account(self, service, password=None, transport=None):
        import secrets

        svc = self._service(service)
        password = password or secrets.token_urlsafe(16)
        self._call(
            svc.server,
            "createacct",
            {"username": svc.svc_username, "domain": svc.primary_domain, "password": password, "plan": self._plan(svc)},
            transport,
        )
        return {"created": svc.svc_username, "password": password}

    def suspend_account(self, service, transport=None):
        svc = self._service(service)
        self._call(svc.server, "suspendacct", {"user": svc.svc_username}, transport)
        return {"suspended": svc.svc_username}

    def unsuspend_account(self, service, transport=None):
        svc = self._service(service)
        self._call(svc.server, "unsuspendacct", {"user": svc.svc_username}, transport)
        return {"unsuspended": svc.svc_username}

    def terminate_account(self, service, transport=None):
        svc = self._service(service)
        self._call(svc.server, "removeacct", {"user": svc.svc_username}, transport)
        return {"terminated": svc.svc_username}

    def change_password(self, service, password, transport=None):
        svc = self._service(service)
        self._call(svc.server, "passwd", {"user": svc.svc_username, "password": password}, transport)
        return {"changed": svc.svc_username}

    def change_package(self, service, new_plan, transport=None):
        svc = self._service(service)
        self._call(svc.server, "changepackage", {"user": svc.svc_username, "pkg": new_plan}, transport)
        return {"plan": new_plan, "service": svc.name}

    def get_usage(self, service, transport=None):
        svc = self._service(service)
        out = self._call(svc.server, "showbw", {"search": svc.svc_username}, transport)
        return {"disk": out.get("diskused", 0), "bandwidth": out.get("bwused", 0)}

    def test_connection(self, server, transport=None):
        self._call(server, "myprivs", {}, transport)
        doc = server if not isinstance(server, str) else frappe.get_doc("Server", server)
        return {"ok": True, "server": doc.name}

    def get_client_area(self, service):
        svc = self._service(service)
        host = self._panel_host(svc)
        if not host:
            return {"panels": [], "buttons": []}
        return {
            "panels": [],
            "buttons": [
                {"key": "panel", "label": "Open cPanel", "kind": "link", "url": f"https://{host}:2083"},
                {"key": "webmail", "label": "Webmail", "kind": "link", "url": f"https://{host}:2096"},
            ],
        }

    def _panel_host(self, svc):
        try:
            if not svc.server or not frappe.db.exists("Server", svc.server):
                return ""
            doc = frappe.get_doc("Server", svc.server)
            return (doc.ip_address or doc.hostname or "").strip()
        except Exception:
            return ""

    def _plan(self, svc):
        try:
            plan = frappe.get_doc("Hosting Plan", svc.hosting_plan) if svc.hosting_plan else None
            return (plan.plan_name if plan else "") or "default"
        except Exception:
            return "default"
