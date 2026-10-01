from .base import ProvisioningAdapter


class PleskAdapter(ProvisioningAdapter):
    adapter_name = "Plesk"

    def create_account(self, service):
        return {"created": service}

    def suspend_account(self, service):
        return {"suspended": service}

    def unsuspend_account(self, service):
        return {"unsuspended": service}

    def terminate_account(self, service):
        return {"terminated": service}

    def change_password(self, service, password):
        return {"changed": service}

    def change_package(self, service, new_plan):
        return {"plan": new_plan, "service": service}

    def get_usage(self, service):
        return {"disk": 0, "bandwidth": 0}

    def test_connection(self, server):
        return {"ok": True, "server": server}
