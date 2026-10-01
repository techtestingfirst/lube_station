from .base import ProvisioningAdapter


class _Stub(ProvisioningAdapter):
    def create_account(self, service):
        raise NotImplementedError("Phase 2/3 adapter inactive")

    def suspend_account(self, service):
        raise NotImplementedError

    def unsuspend_account(self, service):
        raise NotImplementedError

    def terminate_account(self, service):
        raise NotImplementedError

    def change_password(self, service, password):
        raise NotImplementedError

    def change_package(self, service, new_plan):
        raise NotImplementedError

    def get_usage(self, service):
        raise NotImplementedError

    def test_connection(self, server):
        raise NotImplementedError


class VirtualizorAdapter(_Stub):
    adapter_name = "Virtualizor"


class ProxmoxAdapter(_Stub):
    adapter_name = "Proxmox VE"


class HetznerCloudAdapter(_Stub):
    adapter_name = "Hetzner Cloud"


class AwsEc2Adapter(_Stub):
    adapter_name = "AWS EC2"


class CloudflareAdapter(_Stub):
    adapter_name = "Cloudflare"
