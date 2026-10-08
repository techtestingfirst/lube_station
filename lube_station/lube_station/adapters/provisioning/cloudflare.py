"""Live Cloudflare adapter (API v4, Bearer token).

Sandbox by default (no separate host; test with a scoped token). Shapes per
Cloudflare v4 docs: token verify, zone create/delete/get-by-name, full DNS
record CRUD. Suspend/password/package/usage have no Cloudflare equivalent
and throw explicitly. Nothing fires without a Server API token.
"""

import time

import frappe

from .base import ProvisioningAdapter

BASE = "https://api.cloudflare.com/client/v4"
TIMEOUT = 20
RETRIES = 3


def _http(method, url, headers, body, timeout):
    import requests

    return requests.request(method, url, headers=headers, data=body, timeout=timeout)


class CloudflareAdapter(ProvisioningAdapter):
    adapter_name = "Cloudflare"

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
        if not svc.primary_domain:
            frappe.throw(f"Service {svc.name} has no primary domain")
        return svc

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
        frappe.throw(f"Cloudflare {method} {path} failed after {RETRIES} attempts: {last_error}")

    def _result(self, method, path, resp):
        if getattr(resp, "status_code", 200) >= 500:
            raise ConnectionError(f"HTTP {resp.status_code}")
        try:
            out = resp.json() if hasattr(resp, "json") else {}
        except Exception:
            frappe.throw(f"Cloudflare {method} {path} returned non-JSON response")
        if not isinstance(out, dict) or out.get("success") is not True:
            errs = (out.get("errors") or [{}]) if isinstance(out, dict) else [{}]
            frappe.throw(f"Cloudflare {path} rejected: {errs[0].get('message', errs)}", frappe.ValidationError)
        return out.get("result")

    def _zone_id(self, server, domain, transport):
        out = self._call(server, "GET", f"/zones?name={domain}", transport=transport)
        zones = out if isinstance(out, list) else []
        if not zones:
            frappe.throw(f"Cloudflare has no zone for {domain}", frappe.ValidationError)
        return zones[0]["id"]

    # -- lifecycle ------------------------------------------------------
    def create_account(self, service, transport=None):
        svc = self._service(service)
        out = self._call(svc.server, "POST", "/zones", {"name": svc.primary_domain}, transport)
        return {"created": svc.primary_domain, "zone_id": (out or {}).get("id", "")}

    def suspend_account(self, service, transport=None):
        frappe.throw("Cloudflare has no suspend; pause proxying in the dashboard")

    def unsuspend_account(self, service, transport=None):
        frappe.throw("Cloudflare has no unsuspend; resume proxying in the dashboard")

    def terminate_account(self, service, transport=None):
        svc = self._service(service)
        zone_id = self._zone_id(svc.server, svc.primary_domain, transport)
        self._call(svc.server, "DELETE", f"/zones/{zone_id}", transport=transport)
        return {"terminated": svc.primary_domain}

    def change_password(self, service, password, transport=None):
        frappe.throw("Cloudflare has no password API")

    def change_package(self, service, new_plan, transport=None):
        frappe.throw("Cloudflare has no plan API; change the plan in the dashboard")

    def get_usage(self, service, transport=None):
        frappe.throw("Cloudflare usage lives in analytics, not this adapter")

    def test_connection(self, server, transport=None):
        out = self._call(server, "GET", "/user/tokens/verify", transport=transport)
        doc = server if not isinstance(server, str) else frappe.get_doc("Server", server)
        return {"ok": True, "server": doc.name, "token": (out or {}).get("id", "")}

    # -- dns --------------------------------------------------------------
    def add_record(self, service, record, transport=None):
        svc = self._service(service)
        zone_id = self._zone_id(svc.server, svc.primary_domain, transport)
        record = record or {}
        out = self._call(
            svc.server,
            "POST",
            f"/zones/{zone_id}/dns_records",
            {
                "type": record.get("type", "A"),
                "name": record.get("name") or svc.primary_domain,
                "content": record.get("content", ""),
                "ttl": int(record.get("ttl") or 3600),
                "proxied": bool(record.get("proxied", False)),
            },
            transport,
        )
        return {"created": True, "id": (out or {}).get("id", "")}

    def delete_record(self, service, record_id, transport=None):
        svc = self._service(service)
        zone_id = self._zone_id(svc.server, svc.primary_domain, transport)
        self._call(svc.server, "DELETE", f"/zones/{zone_id}/dns_records/{record_id}", transport=transport)
        return {"deleted": True}
