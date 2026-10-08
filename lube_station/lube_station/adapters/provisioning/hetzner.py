"""Live Hetzner Cloud adapter (hcloud REST, Bearer token).

Shapes per Hetzner Cloud API docs: server create/power/delete, rebuild with
image, type change, password reset, metrics, console request. Test against a
project token first (manual gate); nothing fires without a Server API token.
"""

import time

import frappe

from .base import ProvisioningAdapter

BASE = "https://api.hetzner.cloud/v1"
TIMEOUT = 25
RETRIES = 3


def _http(method, url, headers, body, timeout):
    import requests

    return requests.request(method, url, headers=headers, data=body, timeout=timeout)


class HetznerCloudAdapter(ProvisioningAdapter):
    adapter_name = "Hetzner Cloud"

    # -- connection -----------------------------------------------------
    def _server(self, server):
        doc = frappe.get_doc("Server", server) if isinstance(server, str) else server
        token = doc.get_password(fieldname="api_secret", raise_exception=False)
        if not token:
            frappe.throw(f"Server {doc.name} has no API token")
        return doc, token

    def _service(self, service):
        svc = frappe.get_doc("Service", service) if isinstance(service, str) else service
        if not svc.server:
            frappe.throw(f"Service {svc.name} has no server assigned")
        return svc

    def _server_id(self, svc):
        ref = (svc.get("vendor_ref") if hasattr(svc, "get") else None) or getattr(svc, "vendor_ref", "")
        if not ref:
            frappe.throw(f"Service {svc.name} has no vendor reference yet")
        return ref

    # -- transport ------------------------------------------------------
    def _call(self, server, method, path, payload=None, transport=None):
        import json

        doc, token = self._server(server)
        transport = transport or _http
        last_error = None
        for attempt in range(1, RETRIES + 1):
            try:
                resp = transport(
                    method,
                    f"{BASE}{path}",
                    {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                    json.dumps(payload or {}),
                    TIMEOUT,
                )
                return self._result(method, path, resp)
            except frappe.ValidationError:
                raise
            except Exception as e:
                last_error = e
                time.sleep(min(2**attempt, 8))
        frappe.throw(f"Hetzner {method} {path} failed after {RETRIES} attempts: {last_error}")

    def _result(self, method, path, resp):
        if getattr(resp, "status_code", 200) >= 500:
            raise ConnectionError(f"HTTP {resp.status_code}")
        try:
            out = resp.json() if hasattr(resp, "json") else {}
        except Exception:
            frappe.throw(f"Hetzner {method} {path} returned non-JSON response")
        if getattr(resp, "status_code", 200) >= 300:
            detail = out.get("message", out) if isinstance(out, dict) else out
            error = out.get("error", {}) if isinstance(out, dict) else {}
            frappe.throw(
                f"Hetzner {path} rejected: {error.get('message', detail)}", frappe.ValidationError
            )
        return out if isinstance(out, dict) else {}

    # -- lifecycle ------------------------------------------------------
    def create_account(self, service, password=None, image=None, server_type=None, location=None, transport=None):
        import secrets

        svc = self._service(service)
        password = password or secrets.token_urlsafe(16)
        customer = frappe.get_doc("Hosting Customer", svc.customer)
        email = frappe.db.get_value("User", customer.user, "email") or customer.user
        data = {
            "name": (svc.primary_domain or svc.name).lower().replace("_", "-")[:63],
            "server_type": server_type or "cx22",
            "image": image or "ubuntu-24.04",
            "labels": {"lube-service": svc.name, "lube-customer": svc.customer},
            "user_data": f"#cloud-config\npassword: {password}\nchpasswd: {{expire: False}}\nssh_pwauth: True\n",
            "public_net": {"enable_ipv4": True, "enable_ipv6": True},
        }
        if location:
            data["location"] = location
        out = self._call(svc.server, "POST", "/servers", data, transport)
        server = out.get("server") or {}
        return {"created": svc.name, "server_id": server.get("id", ""), "password": password}

    def _action(self, service, action, payload=None, transport=None):
        svc = self._service(service)
        out = self._call(
            svc.server, "POST", f"/servers/{self._server_id(svc)}/actions/{action}", payload or {}, transport
        )
        return out.get("action", {})

    def start(self, service, transport=None):
        self._action(service, "poweron", transport=transport)
        return {"action": "start", "service": service if isinstance(service, str) else service.name}

    def stop(self, service, transport=None):
        self._action(service, "shutdown", transport=transport)
        return {"action": "stop", "service": service if isinstance(service, str) else service.name}

    def restart(self, service, transport=None):
        self._action(service, "reboot", transport=transport)
        return {"action": "restart", "service": service if isinstance(service, str) else service.name}

    def poweroff(self, service, transport=None):
        self._action(service, "poweroff", transport=transport)
        return {"action": "poweroff", "service": service if isinstance(service, str) else service.name}

    def suspend_account(self, service, transport=None):
        self._action(service, "poweroff", transport=transport)
        return {"suspended": service if isinstance(service, str) else service.name}

    def unsuspend_account(self, service, transport=None):
        self._action(service, "poweron", transport=transport)
        return {"unsuspended": service if isinstance(service, str) else service.name}

    def terminate_account(self, service, transport=None):
        svc = self._service(service)
        self._call(svc.server, "DELETE", f"/servers/{self._server_id(svc)}", transport=transport)
        return {"terminated": svc.name}

    def rebuild(self, service, image=None, password=None, transport=None):
        import secrets

        svc = self._service(service)
        password = password or secrets.token_urlsafe(16)
        data = {"image": image or "ubuntu-24.04"}
        self._call(svc.server, "POST", f"/servers/{self._server_id(svc)}/actions/rebuild", data, transport)
        return {"rebuilt": svc.name, "password": password}

    def change_password(self, service, password, transport=None):
        svc = self._service(service)
        self._call(
            svc.server, "POST", f"/servers/{self._server_id(svc)}/actions/reset_password", {"password": password}, transport
        )
        return {"changed": svc.name}

    def change_package(self, service, new_plan, transport=None):
        svc = self._service(service)
        self._call(
            svc.server,
            "POST",
            f"/servers/{self._server_id(svc)}/actions/change_type",
            {"server_type": new_plan, "upgrade_disk": False},
            transport,
        )
        return {"plan": new_plan, "service": svc.name}

    def get_usage(self, service, transport=None):
        import datetime

        svc = self._service(service)
        end = datetime.datetime.now(datetime.timezone.utc)
        start = end - datetime.timedelta(hours=1)
        out = self._call(
            svc.server,
            "GET",
            f"/servers/{self._server_id(svc)}/metrics?type=cpu,disk,network&start={start.isoformat()}&end={end.isoformat()}",
            transport=transport,
        )
        series = ((out.get("metrics") or {}).get("time_series")) or {}

        def latest(*needles):
            for key, val in series.items():
                if all(n in str(key).lower() for n in needles):
                    values = (val or {}).get("values") or []
                    if values:
                        return values[-1][1]
            return "0"

        return {
            "cpu": latest("cpu"),
            "disk": latest("disk"),
            "bandwidth": latest("network") or latest("bandwidth"),
        }

    def console(self, service, transport=None):
        svc = self._service(service)
        out = self._call(svc.server, "POST", f"/servers/{self._server_id(svc)}/actions/request_console", {"wss": True}, transport)
        return {"wss_url": out.get("wss_url", ""), "password": out.get("password", "")}

    def test_connection(self, server, transport=None):
        out = self._call(server, "GET", "/datacenters", transport=transport)
        doc = server if not isinstance(server, str) else frappe.get_doc("Server", server)
        names = [d.get("name", "") for d in (out.get("datacenters") or [])]
        return {"ok": True, "server": doc.name, "datacenters": names}
