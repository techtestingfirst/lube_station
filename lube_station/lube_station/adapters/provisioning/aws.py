"""Live AWS EC2 adapter (Query API + SigV4, no SDK needed).

Region default us-east-1, creds from Lube Station Settings. SigV4 signing
follows the AWS spec (verified against the documented IAM example vector in
tests). Run/Start/Stop/Reboot/Terminate/ModifyType/Describe/ConsoleOutput
are implemented; reinstall/password/usage have no EC2 equivalent and throw
explicitly (usage lives in CloudWatch). Nothing fires without keys.
"""

import datetime
import hashlib
import hmac
import time

import frappe

from lube_station.lube_station.settings import get_setting

from .base import ProvisioningAdapter

VERSION = "2016-11-15"
SERVICE = "ec2"
TIMEOUT = 25
RETRIES = 3


def _http_post(url, headers, body, timeout):
    import requests

    return requests.post(url, headers=headers, data=body, timeout=timeout)


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode(), hashlib.sha256).digest()


def sign_request(secret: str, region: str, method: str, host: str, path: str,
                 query: str, body: str, when: datetime.datetime, service: str = SERVICE) -> dict:
    """SigV4 auth headers for one request. Signs host + x-amz-date only.
    Pure function apart from time input; unit-tested."""
    amzdate = when.strftime("%Y%m%dT%H%M%SZ")
    datestamp = when.strftime("%Y%m%d")
    headers = {"host": host, "x-amz-date": amzdate}
    signed = "host;x-amz-date"
    canonical_headers = "".join(f"{k}:{str(headers[k]).strip()}\n" for k in sorted(headers))
    canonical = "\n".join([method, path, query, canonical_headers, signed, _sha256(body)])
    scope = f"{datestamp}/{region}/{service}/aws4_request"
    string_to_sign = "\n".join(["AWS4-HMAC-SHA256", amzdate, scope, _sha256(canonical)])
    signing = _sign(f"AWS4{secret}".encode(), datestamp)
    for part in (region, service, "aws4_request"):
        signing = hmac.new(signing, part.encode(), hashlib.sha256).digest()
    signature = hmac.new(signing, string_to_sign.encode(), hashlib.sha256).hexdigest()
    return {"X-Amz-Date": amzdate, "scope": scope, "signature": signature, "signed": signed}



def _text(root, *names: str) -> str:
    """First matching local tag name, any namespace."""
    for name in names:
        el = root.find(f".//{{*}}{name}")
        if el is not None and (el.text or "").strip():
            return el.text.strip()
    return ""


def _all(root, name: str) -> list:
    return [el.text for el in root.findall(f".//{{*}}{name}") if el.text]


class AwsEc2Adapter(ProvisioningAdapter):
    adapter_name = "AWS EC2"

    # -- connection -----------------------------------------------------
    def _creds(self):
        key_id = (get_setting("aws_access_key_id") or "").strip()
        secret = (get_setting("aws_secret_access_key") or "").strip()
        region = (get_setting("aws_region") or "us-east-1").strip() or "us-east-1"
        if not key_id or not secret:
            frappe.throw("AWS not configured: set access key/secret in Lube Station Settings")
        return key_id, secret, region

    def _service(self, service):
        svc = frappe.get_doc("Service", service) if isinstance(service, str) else service
        if not svc.server:
            frappe.throw(f"Service {svc.name} has no server assigned")
        return svc

    def _instance_id(self, svc):
        ref = (svc.get("vendor_ref") if hasattr(svc, "get") else None) or getattr(svc, "vendor_ref", "")
        if not ref:
            frappe.throw(f"Service {svc.name} has no vendor reference yet")
        return ref

    # -- transport ------------------------------------------------------
    def _call(self, action: str, params: dict, transport=None):
        import urllib.parse

        key_id, secret, region = self._creds()
        transport = transport or _http_post
        host = f"ec2.{region}.amazonaws.com"
        body = urllib.parse.urlencode({"Action": action, "Version": VERSION, **(params or {})})
        headers = {"Content-Type": "application/x-www-form-urlencoded; charset=utf-8", "Host": host}
        when = datetime.datetime.now(datetime.timezone.utc)
        signed = sign_request(secret, region, "POST", host, "/", "", body, when)
        headers["X-Amz-Date"] = signed["X-Amz-Date"]
        headers["Authorization"] = (
            f"AWS4-HMAC-SHA256 Credential={key_id}/{signed['scope']}, SignedHeaders={signed['signed']}, Signature={signed['signature']}"
        )
        last_error = None
        for attempt in range(1, RETRIES + 1):
            try:
                resp = transport(f"https://{host}/", headers, body, TIMEOUT)
                return self._result(action, resp)
            except frappe.ValidationError:
                raise
            except Exception as e:
                last_error = e
                time.sleep(min(2**attempt, 8))
        frappe.throw(f"AWS EC2 {action} failed after {RETRIES} attempts: {last_error}")

    def _result(self, action, resp):
        if getattr(resp, "status_code", 200) >= 500:
            raise ConnectionError(f"HTTP {resp.status_code}")
        try:
            import xml.etree.ElementTree as ET

            root = ET.fromstring(resp.text if hasattr(resp, "text") else resp)
        except Exception:
            frappe.throw(f"AWS EC2 {action} returned non-XML response")
        if root.tag.endswith("Response"):
            errors = root.find(".//{*}Errors") or root.find(".//{*}Error")
            if errors is not None:
                msg = _text(errors, "Message") or "unknown"
                frappe.throw(f"AWS EC2 {action} rejected: {msg}", frappe.ValidationError)
            return root
        errors = root.find(".//{*}Error")
        if errors is not None:
            frappe.throw(f"AWS EC2 {action} rejected: {_text(errors, 'Message')}", frappe.ValidationError)
        return root

    # -- lifecycle ------------------------------------------------------
    def create_account(self, service, image=None, instance_type=None, key_name=None, transport=None):
        svc = self._service(service)
        params = {
            "ImageId": image or "ami-0c55b159cbfafe1f0",
            "MinCount": 1,
            "MaxCount": 1,
            "InstanceType": instance_type or "t3.micro",
            "TagSpecifications.1.ResourceType": "instance",
            f"TagSpecifications.1.Tag.1.Value": svc.name,
            "TagSpecifications.1.Tag.1.Key": "lube-service",
        }
        if key_name:
            params["KeyName"] = key_name
        root = self._call("RunInstances", params, transport)
        iid = _text(root, "instanceId")
        return {"created": svc.name, "instance_id": iid}

    def _power(self, service, action, transport=None):
        svc = self._service(service)
        root = self._call(action, {"InstanceId.1": self._instance_id(svc)}, transport)
        state = _text(root, "name") or action
        return {"action": action, "service": svc.name, "state": state}

    def start(self, service, transport=None):
        return self._power(service, "StartInstances", transport)

    def stop(self, service, transport=None):
        return self._power(service, "StopInstances", transport)

    def restart(self, service, transport=None):
        return self._power(service, "RebootInstances", transport)

    def poweroff(self, service, transport=None):
        return self.stop(service, transport)

    def suspend_account(self, service, transport=None):
        return self.stop(service, transport)

    def unsuspend_account(self, service, transport=None):
        return self.start(service, transport)

    def terminate_account(self, service, transport=None):
        svc = self._service(service)
        self._call("TerminateInstances", {"InstanceId.1": self._instance_id(svc)}, transport)
        return {"terminated": svc.name}

    def rebuild(self, service, image=None, transport=None):
        frappe.throw("EC2 has no reinstall call; terminate and run a fresh instance instead")

    def change_password(self, service, password, transport=None):
        frappe.throw("EC2 has no password API; use key pairs or user-data")

    def change_package(self, service, new_plan, transport=None):
        svc = self._service(service)
        self._call(
            "ModifyInstanceAttribute",
            {"InstanceId": self._instance_id(svc), "InstanceType.Value": new_plan},
            transport,
        )
        return {"plan": new_plan, "service": svc.name}

    def get_usage(self, service, transport=None):
        frappe.throw("EC2 usage lives in CloudWatch, not the EC2 API")

    def console(self, service, transport=None):
        svc = self._service(service)
        root = self._call("GetConsoleOutput", {"InstanceId": self._instance_id(svc)}, transport)
        return {"output": _text(root, "output")}

    def test_connection(self, server, transport=None):
        doc = server if not isinstance(server, str) else frappe.get_doc("Server", server)
        root = self._call("DescribeRegions", {"AllRegions": "false"}, transport)
        regions = _all(root, "regionName")
        return {"ok": True, "server": doc.name, "regions": regions}
