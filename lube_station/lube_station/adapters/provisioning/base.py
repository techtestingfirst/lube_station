class ProvisioningAdapter:
    adapter_name = ""

    def create_account(self, service):
        raise NotImplementedError

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
