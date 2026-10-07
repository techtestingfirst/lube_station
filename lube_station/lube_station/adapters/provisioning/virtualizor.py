"""Live Virtualizor adapter (Admin API over HTTPS, key auth).

Shapes follow the official Virtualizor Admin API docs: act=addvs for
create, act=vs power actions, suspend/unsuspend/delete siblings, rebuild
with osid, listvs for usage/test. api=json yields JSON. Password/package
changes have no verified admin shape and throw explicitly. Nothing is
contacted until a Server row holds API creds (manual gate).
"""

import time
import urllib.parse

import frappe

from .base import ProvisioningAdapter

PORT = 4085
TIMEOUT = 25
RETRIES = 3


def _http(method, url, headers, body, timeout):
    import requests

    return requests.request(method, url, headers=headers, data=body, timeout=timeout)


class VirtualizorAdapter(ProvisioningAdapter):
    adapter_name = "Virtualizor"

    # -- connection -----------------------------------------------------
    def _server(self, server):
        doc = frappe.get_doc("Server", server) if isinstance(server, str) else server
        host = (doc.ip_address or doc.hostname or "").strip()
        if not host:
            frappe.throw(f"Server {doc.name} has no hostname/IP")
        key = (doc.api_username or "").strip()
        token = doc.get_password(fieldname="api_secret", raise_exception=False)
        if not key or not token:
            frappe.throw(f"Server {doc.name} has no API credentials")
        return doc, host, key, token

    def _service(self, service):
        svc = frappe.get_doc("Service", service) if isinstance(service, str) else service
        if not svc.server:
            frappe.throw(f"Service {svc.name} has no server assigned")
        return svc

    def _vpsid(self, svc):
        vpsid = (svc.get("vendor_ref") if hasattr(svc, "get") else None) or getattr(svc, "vendor_ref", "")
        if not vpsid:
            frappe.throw(f"Service {svc.name} has no vendor reference yet")
        return vpsid

    # -- transport ------------------------------------------------------
    def _call(self, server, act, params=None, transport=None, post=None):
        doc, host, key, token = self._server(server)
        transport = transport or _http
        query = {"act": act, "adminapikey": key, "adminapipass": token, "api": "json"}
        if post is None:
            query.update(params or {})
            url = f"https://{host}:{PORT}/index.php?" + urllib.parse.urlencode(query)
            body, method = None, "GET"
        else:
            url = f"https://{host}:{PORT}/index.php?" + urllib.parse.urlencode(query)
            body = urllib.parse.urlencode(post or {})
            method = "POST"
        last_error = None
        for attempt in range(1, RETRIES + 1):
            try:
                resp = transport(method, url, {}, body, TIMEOUT)
                return self._result(doc, act, resp)
            except frappe.ValidationError:
                raise
            except Exception as e:
                last_error = e
                time.sleep(min(2**attempt, 8))
        frappe.throw(f"Virtualizor {act} failed after {RETRIES} attempts: {last_error}")

    def _result(self, server_doc, act, resp):
        if getattr(resp, "status_code", 200) >= 500:
            raise ConnectionError(f"HTTP {resp.status_code}")
        try:
            out = resp.json() if hasattr(resp, "json") else {}
        except Exception:
            frappe.throw(f"Virtualizor {act} returned non-JSON response")
        if isinstance(out, dict) and out.get("error"):
            errs = out["error"] if isinstance(out["error"], list) else [out["error"]]
            if any(errs):
                frappe.throw(f"Virtualizor {act} rejected: {errs}", frappe.ValidationError)
        return out if isinstance(out, dict) else {}

    # -- lifecycle ------------------------------------------------------
    def create_account(self, service, password=None, osid=None, ips=None, virt="kvm", transport=None):
        import secrets

        svc = self._service(service)
        password = password or secrets.token_urlsafe(16)
        cfg = None
        if getattr(svc, "hosting_plan", ""):
            cfg_name = frappe.db.get_value("VPS Configuration", {"hosting_plan": svc.hosting_plan}, "name")
            cfg = frappe.get_doc("VPS Configuration", cfg_name) if cfg_name else None
        customer = frappe.get_doc("Hosting Customer", svc.customer)
        email = frappe.db.get_value("User", customer.user, "email") or customer.user
        post = {
            "virt": virt,
            "hostname": svc.primary_domain or svc.name,
            "rootpass": password,
            "user_email": email,
            "user_pass": password,
            "osid": osid or "",
            "ips": list(ips or []),
            "ram": cfg.ram_mb if cfg else "",
            "space": cfg.storage_gb if cfg else "",
            "bandwidth": (cfg.bandwidth_gb * 1024) if cfg and cfg.bandwidth_gb else 0,
            "cores": cfg.cpu_cores if cfg else "",
            "addvps": 1,
        }
        out = self._call(svc.server, "addvs", post={k: v for k, v in post.items() if v != ""}, transport=transport)
        info = out.get("vs_info") or {}
        return {"created": svc.name, "vpsid": info.get("vpsid", ""), "password": password}
    def _power(self, service, action, transport=None):
        svc = self._service(service)
        out = self._call(
            svc.server, "vs", {"action": action, "vpsid": self._vpsid(svc)}, transport=transport
        )
        if not out.get("done"):
            frappe.throw(f"Virtualizor {action} failed for {svc.name}", frappe.ValidationError)
        return {"action": action, "service": svc.name}

    def suspend_account(self, service, transport=None):
        svc = self._service(service)
        out = self._call(svc.server, "vs", {"suspend": self._vpsid(svc)}, transport=transport)
        if not out.get("done"):
            frappe.throw(f"Virtualizor suspend failed for {svc.name}", frappe.ValidationError)
        return {"suspended": svc.name}

    def unsuspend_account(self, service, transport=None):
        svc = self._service(service)
        out = self._call(svc.server, "vs", {"unsuspend": self._vpsid(svc)}, transport=transport)
        if not out.get("done"):
            frappe.throw(f"Virtualizor unsuspend failed for {svc.name}", frappe.ValidationError)
        return {"unsuspended": svc.name}

    def terminate_account(self, service, transport=None):
        svc = self._service(service)
        out = self._call(svc.server, "vs", {"delete": self._vpsid(svc)}, transport=transport)
        if not out.get("done"):
            frappe.throw(f"Virtualizor delete failed for {svc.name}", frappe.ValidationError)
        return {"terminated": svc.name}

    def start(self, service, transport=None):
        return self._power(service, "start", transport)

    def stop(self, service, transport=None):
        return self._power(service, "stop", transport)

    def restart(self, service, transport=None):
        return self._power(service, "restart", transport)

    def poweroff(self, service, transport=None):
        return self._power(service, "poweroff", transport)

    def rebuild(self, service, osid, password=None, transport=None):
        import secrets

        svc = self._service(service)
        password = password or secrets.token_urlsafe(16)
        out = self._call(
            svc.server,
            "rebuild",
            {"vpsid": self._vpsid(svc), "reos": 1, "osid": osid, "newpass": password, "conf": password},
            transport=transport,
        )
        if not out.get("done"):
            frappe.throw(f"Virtualizor rebuild failed for {svc.name}", frappe.ValidationError)
        return {"rebuilt": svc.name, "password": password}

    def change_password(self, service, password, transport=None):
        frappe.throw("Virtualizor admin password change has no verified shape; use rebuild with a new password")

    def change_package(self, service, new_plan, transport=None):
        frappe.throw("Virtualizor plan change has no verified shape; recreate the VPS on the new plan")

    def get_usage(self, service, transport=None):
        svc = self._service(service)
        out = self._call(svc.server, "listvs", {"vpsid": self._vpsid(svc)}, transport=transport)
        vs = out.get("vs") or {}
        entry = vs.get(str(self._vpsid(svc)), {}) if isinstance(vs, dict) else {}
        return {
            "disk": entry.get("used_bandwidth", entry.get("space", 0)),
            "bandwidth": entry.get("used_bandwidth", 0),
        }

    def test_connection(self, server, transport=None):
        self._call(server, "listvs", {}, transport=transport)
        doc = server if not isinstance(server, str) else frappe.get_doc("Server", server)
        return {"ok": True, "server": doc.name}
