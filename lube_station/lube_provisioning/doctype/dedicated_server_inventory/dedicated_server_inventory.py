from frappe.model.document import Document


class DedicatedServerInventory(Document):
    # begin: auto-generated types
    # This code is auto-generated. Do not modify anything in this block.

    from typing import TYPE_CHECKING

    if TYPE_CHECKING:
        from frappe.types import DF

        asset_id: DF.Data | None
        assigned_service: DF.Data | None
        bandwidth_mbps: DF.Int
        cpu: DF.Data | None
        ip_pool: DF.SmallText | None
        lease_expiry: DF.Datetime | None
        lease_key: DF.Data | None
        location: DF.Data | None
        provider: DF.Link | None
        ram_gb: DF.Int
        status: DF.Literal["Available", "Reserved", "Assigned", "Wipe Pending", "Terminated"]
        storage_json: DF.Code | None
    # end: auto-generated types

    pass
