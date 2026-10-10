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

    def create_sso_session(self, service):
        """One-time panel login URL for an owned service.

        Returns {"url": ...}. Implementations must use server-side API
        creds only, never expose secrets, and return a short-lived URL.
        """
        raise NotImplementedError

    def get_client_area(self, service):
        """Customer-portal controls supplied by the module (WHMCS parity).

        Returns {"panels": [...], "buttons": [...]} with link-only buttons
        (no secrets, no live calls). Each button: {"key", "label", "kind",
        "url" | "action"}. kind "link" opens url; kind "vps" calls the
        existing vps_control API with action. Base default: nothing.
        """
        return {"panels": [], "buttons": []}
