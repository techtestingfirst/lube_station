"""Live Proxmox VE adapter (api2/json, token or ticket auth).

Sandbox by default (no separate host; test against a lab node). Auth prefers
API tokens (api_username as user@realm!tokenid, api_secret as the secret);
otherwise falls back to ticket auth (cookie + CSRF header). Shapes per
Proxmox VE API docs: qemu create/power/delete, vncproxy, current status,
version check. Rebuild has no single call and is explicit. Nothing connects
without Server creds (manual gate).
"""

import time

import frappe

from .base import ProvisioningAdapter

PORT = 8006
TIMEOUT = 25
RETRIES = 3


def _http(method, url, headers, body, timeout, cookies=None):
    import requests

    return requests.request(method, url, headers=headers, data=body, cookies=cookies, timeout=timeout, verify=False)


class ProxmoxAdapter(ProvisioningAdapter):
    adapter_name = "Proxmox VE"

    # -- connection -----------------------------------------------------
    def _server(self, server):
        doc = frappe.get_doc("Server", server) if isinstance(server, str) else server
        host = (doc.ip_address or doc.hostname or "").strip()
        if not host:
            frappe.throw(f"Server {doc.name} has no hostname/IP")
        user = (doc.api_username or "").strip()
        secret = doc.get_password(fieldname="api_secret", raise_exception=False)
        if not user or not secret:
            frappe.throw(f"Server {doc.name} has no API credentials")
        return doc, host, user, secret

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

    def _node(self, svc):
        node = getattr(svc, "node", "") or (svc.get("node") if hasattr(svc, "get") else "")
        if not node:
            frappe.throw(f"Service {svc.name} has no Proxmox node set (use node field)")
        return node

    # -- transport ------------------------------------------------------
    def _auth(self, server, transport=None):
        doc, host, user, secret = self._server(server)
        transport = transport or _http
        base = f"https://{host}:{PORT}/api2/json"
        if "!" in user:
            return base, {"Authorization": f"PVEAPIToken={user}={secret}"}, {}, transport
        out = transport(
            "POST",
            f"{base}/access/ticket",
            {"Content-Type": "application/x-www-form-urlencoded"},
            f"username={user}&password={secret}",
            TIMEOUT,
        )
        data = (out.json() if hasattr(out, "json") else {}).get("data") or {}
        if not data.get("ticket"):
            frappe.throw(f"Proxmox ticket auth failed for {doc.name}", frappe.ValidationError)
        return (
            base,
            {"CSRFPreventionToken": data.get("CSRFPreventionToken", "")},
            {"PVEAuthCookie": data.get("ticket", "")},
            transport,
        )

    def _call(self, server, method, path, payload=None, transport=None):
        import json
        import urllib.parse

        base, headers, cookies, transport = self._auth(server, transport)
        headers = dict(headers, **{"Content-Type": "application/x-www-form-urlencoded"})
        if method == "GET" and payload:
            url = f"{base}{path}?" + urllib.parse.urlencode(payload)
            body = None
        else:
            url = f"{base}{path}"
            body = urllib.parse.urlencode(payload or {}) or None
        last_error = None
        for attempt in range(1, RETRIES + 1):
            try:
                resp = transport(method, url, headers, body, TIMEOUT, cookies or None)
                return self._result(method, path, resp)
            except frappe.ValidationError:
                raise
            except Exception as e:
                last_error = e
                time.sleep(min(2**attempt, 8))
        frappe.throw(f"Proxmox {method} {path} failed after {RETRIES} attempts: {last_error}")

    def _result(self, method, path, resp):
        if getattr(resp, "status_code", 200) >= 500:
            raise ConnectionError(f"HTTP {resp.status_code}")
        try:
            out = resp.json() if hasattr(resp, "json") else {}
        except Exception:
            frappe.throw(f"Proxmox {method} {path} returned non-JSON response")
        if getattr(resp, "status_code", 200) not in (200, 201):
            frappe.throw(f"Proxmox {path} rejected: {out}", frappe.ValidationError)
        return (out or {}).get("data", out)

    # -- lifecycle ------------------------------------------------------
    def create_account(self, service, password=None, node=None, vmid=None, ostemplate=None, transport=None):
        import secrets

        svc = self._service(service)
        password = password or secrets.token_urlsafe(16)
        cfg = None
        if getattr(svc, "hosting_plan", ""):
            cfg_name = frappe.db.get_value("VPS Configuration", {"hosting_plan": svc.hosting_plan}, "name")
            cfg = frappe.get_doc("VPS Configuration", cfg_name) if cfg_name else None
        customer = frappe.get_doc("Hosting Customer", svc.customer)
        email = frappe.db.get_value("User", customer.user, "email") or customer.user
        target_node = node or getattr(svc, "node", "")
        if not target_node:
            frappe.throw(f"Service {svc.name} needs a Proxmox node (pass node=)")
        post = {
            "vmid": vmid or "",
            "name": svc.primary_domain or svc.name,
            "ostemplate": ostemplate or "",
            "password": password,
            "cores": cfg.cpu_cores if cfg else "",
            "memory": cfg.ram_mb if cfg else "",
            "net0": "virtio,bridge=vmbr0",
            "description": f"{svc.name} {email}",
        }
        out = self._call(svc.server, "POST", f"/nodes/{target_node}/qemu", {k: v for k, v in post.items() if v != ""}, transport=transport)
        return {"created": svc.name, "task": (out or ""), "password": password}

    def _power(self, service, action, transport=None):
        svc = self._service(service)
        out = self._call(svc.server, "POST", f"/nodes/{self._node(svc)}/qemu/{self._vpsid(svc)}/status/{action}", transport=transport)
        return {"action": action, "service": svc.name, "task": out}

    def start(self, service, transport=None):
        return self._power(service, "start", transport)

    def stop(self, service, transport=None):
        return self._power(service, "stop", transport)

    def restart(self, service, transport=None):
        return self._power(service, "reboot", transport)

    def poweroff(self, service, transport=None):
        return self._power(service, "shutdown", transport)

    def suspend_account(self, service, transport=None):
        svc = self._service(service)
        out = self._call(svc.server, "POST", f"/nodes/{self._node(svc)}/qemu/{self._vpsid(svc)}/status/suspend", transport=transport)
        return {"suspended": svc.name, "task": out}

    def unsuspend_account(self, service, transport=None):
        svc = self._service(service)
        out = self._call(svc.server, "POST", f"/nodes/{self._node(svc)}/qemu/{self._vpsid(svc)}/status/resume", transport=transport)
        return {"unsuspended": svc.name, "task": out}

    def terminate_account(self, service, transport=None):
        svc = self._service(service)
        out = self._call(svc.server, "DELETE", f"/nodes/{self._node(svc)}/qemu/{self._vpsid(svc)}", transport=transport)
        return {"terminated": svc.name, "task": out}

    def rebuild(self, service, osid=None, password=None, transport=None):
        frappe.throw("Proxmox has no single reinstall call; recreate the VM from template")

    def change_password(self, service, password, transport=None):
        frappe.throw("Proxmox password change has no verified shape; reinstall or use guest agent")

    def change_package(self, service, new_plan, transport=None):
        frappe.throw("Proxmox plan change has no verified shape; resize via config API")

    def get_usage(self, service, transport=None):
        svc = self._service(service)
        out = self._call(svc.server, "GET", f"/nodes/{self._node(svc)}/qemu/{self._vpsid(svc)}/status/current", transport=transport)
        out = out or {}
        return {"disk": out.get("disk", 0), "bandwidth": out.get("netin", 0), "memory": out.get("mem", 0), "uptime": out.get("uptime", 0)}

    def console(self, service, transport=None):
        svc = self._service(service)
        out = self._call(svc.server, "POST", f"/nodes/{self._node(svc)}/qemu/{self._vpsid(svc)}/vncproxy", transport=transport)
        return {"ticket": (out or {}).get("ticket", ""), "port": (out or {}).get("port", "")}

    def test_connection(self, server, transport=None):
        out = self._call(server, "GET", "/version", transport=transport)
        doc = server if not isinstance(server, str) else frappe.get_doc("Server", server)
        return {"ok": True, "server": doc.name, "version": (out or {}).get("version", "")}
