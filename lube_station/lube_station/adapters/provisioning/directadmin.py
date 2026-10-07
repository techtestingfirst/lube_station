"""Live DirectAdmin adapter (legacy CMD_API over HTTPS, Basic auth).

Sandbox by default: credentials come from the Server row (api_username +
api_secret Password field). Command shapes follow the official DirectAdmin
legacy API docs (CMD_API_ACCOUNT_USER / SELECT_USERS / MODIFY_USER /
SHOW_USER_USAGE / SHOW_ALL_USERS / USER_PASSWD). Responses are url-encoded
(error=0/1 with text/details); SELECT_USERS answers with a redirect on
success. Nothing is contacted until a Server row holds real creds.
"""

import time
import urllib.parse

import frappe

from lube_station.lube_station.adapters.utils import redact

from .base import ProvisioningAdapter

PORT = 2222
TIMEOUT = 20
RETRIES = 3


def _http_post(url, headers, body, timeout):
    import requests

    return requests.post(url, headers=headers, data=body, timeout=timeout)


class DirectAdminAdapter(ProvisioningAdapter):
    adapter_name = "DirectAdmin"

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
    def _call(self, server, command, params, transport=None):
        import base64

        doc, host, user, token = self._server(server)
        transport = transport or _http_post
        url = f"https://{host}:{PORT}/{command}?json=yes"
        creds = base64.b64encode(f"{user}:{token}".encode()).decode()
        headers = {"Authorization": f"Basic {creds}", "Content-Type": "application/x-www-form-urlencoded"}
        body = urllib.parse.urlencode({k: v for k, v in (params or {}).items() if v is not None})
        safe = redact(dict(params or {}))
        last_error = None
        for attempt in range(1, RETRIES + 1):
            try:
                resp = transport(url, headers, body, TIMEOUT)
                return self._result(doc, command, safe, resp)
            except frappe.ValidationError:
                raise
            except Exception as e:
                last_error = e
                time.sleep(min(2**attempt, 8))
        self._audit(doc, command, safe, "Failed", str(last_error)[:500])
        frappe.throw(f"DirectAdmin {command} failed after {RETRIES} attempts: {last_error}")

    def _result(self, server_doc, command, safe, resp):
        if getattr(resp, "status_code", 200) >= 500:
            raise ConnectionError(f"HTTP {resp.status_code}")
        text = resp.text if hasattr(resp, "text") else str(resp)
        try:
            out = dict(urllib.parse.parse_qsl(text, keep_blank_values=True))
        except Exception:
            frappe.throw(f"DirectAdmin {command} returned unparseable response")
        if out.get("error") == "1":
            reason = out.get("text") or out.get("details") or "unknown error"
            self._audit(server_doc, command, safe, "Failed", str(reason)[:500])
            frappe.throw(f"DirectAdmin {command} rejected: {reason}", frappe.ValidationError)
        self._audit(server_doc, command, safe, "Success", "")
        return out

    def _audit(self, server_doc, command, safe, status, error_text):
        try:
            provider = frappe.db.get_value("Infrastructure Provider", {"status": "Active"}, "name")
            if not provider or not frappe.db.exists("DocType", "Provider API Log"):
                return
            frappe.get_doc(
                {
                    "doctype": "Provider API Log",
                    "provider": provider,
                    "action": f"directadmin:{command}",
                    "status": status,
                    "error_text": error_text,
                }
            ).insert(ignore_permissions=True)
        except Exception:
            pass

    # -- lifecycle ------------------------------------------------------
    def create_account(self, service, password=None, email=None, transport=None):
        import secrets

        svc = self._service(service)
        password = password or secrets.token_urlsafe(16)
        user_email = email or self._owner_email(svc)
        out = self._call(
            svc.server,
            "CMD_API_ACCOUNT_USER",
            {
                "action": "create",
                "add": "Submit",
                "username": svc.svc_username,
                "email": user_email,
                "passwd": password,
                "passwd2": password,
                "domain": svc.primary_domain,
                "package": self._plan(svc),
                "ip": "shared",
                "notify": "no",
            },
            transport,
        )
        return {"created": svc.svc_username, "password": password, "details": out.get("details", "")}

    def suspend_account(self, service, transport=None):
        svc = self._service(service)
        self._call(
            svc.server,
            "CMD_API_SELECT_USERS",
            {"suspend": "Suspend", "select0": svc.svc_username},
            transport,
        )
        return {"suspended": svc.svc_username}

    def unsuspend_account(self, service, transport=None):
        svc = self._service(service)
        self._call(
            svc.server,
            "CMD_API_SELECT_USERS",
            {"suspend": "Unsuspend", "select0": svc.svc_username},
            transport,
        )
        return {"unsuspended": svc.svc_username}

    def terminate_account(self, service, transport=None):
        svc = self._service(service)
        self._call(
            svc.server,
            "CMD_API_SELECT_USERS",
            {"confirmed": "Confirm", "delete": "yes", "select0": svc.svc_username},
            transport,
        )
        return {"terminated": svc.svc_username}

    def change_password(self, service, password, transport=None):
        svc = self._service(service)
        self._call(
            svc.server,
            "CMD_API_USER_PASSWD",
            {"username": svc.svc_username, "passwd": password, "passwd2": password},
            transport,
        )
        return {"changed": svc.svc_username}

    def change_package(self, service, new_plan, transport=None):
        svc = self._service(service)
        self._call(
            svc.server,
            "CMD_API_MODIFY_USER",
            {"action": "customize", "user": svc.svc_username, "package": new_plan},
            transport,
        )
        return {"plan": new_plan, "service": svc.name}

    def get_usage(self, service, transport=None):
        svc = self._service(service)
        out = self._call(svc.server, "CMD_API_SHOW_USER_USAGE", {"user": svc.svc_username}, transport)
        return {"disk": self._mb(out.get("quota", 0)), "bandwidth": self._mb(out.get("bandwidth", 0))}

    def test_connection(self, server, transport=None):
        self._call(server, "CMD_API_SHOW_ALL_USERS", {}, transport)
        doc = server if not isinstance(server, str) else frappe.get_doc("Server", server)
        return {"ok": True, "server": doc.name}

    # -- helpers ----------------------------------------------------------
    def _plan(self, svc):
        try:
            plan = frappe.get_doc("Hosting Plan", svc.hosting_plan) if svc.hosting_plan else None
            return (plan.plan_name if plan else "") or "default"
        except Exception:
            return "default"

    def _owner_email(self, svc):
        try:
            customer = frappe.get_doc("Hosting Customer", svc.customer)
            return frappe.db.get_value("User", customer.user, "email") or customer.user
        except Exception:
            return f"{svc.svc_username}@example.invalid"

    def _mb(self, value):
        try:
            return float(value or 0)
        except (TypeError, ValueError):
            return 0
