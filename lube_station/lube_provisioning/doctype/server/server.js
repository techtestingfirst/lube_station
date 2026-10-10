frappe.ui.form.on("Server", {
    refresh(frm) {
        // Status headline so connectivity is visible the moment the form opens.
        if (!frm.is_new()) {
            const status = frm.doc.connection_status || "Not Checked";
            const color = status === "Online" ? "green" : status === "Failed" ? "red" : "gray";
            const checked = frm.doc.last_checked_on
                ? `Last checked: ${frm.doc.last_checked_on}`
                : "Never checked";
            const msg = frm.doc.last_check_message ? ` — ${frm.doc.last_check_message}` : "";
            frm.dashboard.clear_headline();
            frm.dashboard.set_headline_alert(
                `Connection: <b>${status}</b> (${checked}${msg})`,
                color === "green" ? "green" : color === "red" ? "red" : "gray"
            );

            frm.add_custom_button(__("Test Connection"), () => {
                frappe.dom.freeze(__("Testing server connection..."));
                frm.call("test_connection").then((r) => {
                    frappe.dom.unfreeze();
                    const res = r.message || {};
                    if (res.ok) {
                        frappe.show_alert({
                            message: __("Connected: {0}", [res.message || "OK"]),
                            indicator: "green",
                        });
                    } else {
                        frappe.msgprint({
                            title: __("Connection Failed"),
                            message: res.message || __("Could not reach server."),
                            indicator: "red",
                        });
                    }
                    frm.reload_doc();
                }).catch(() => frappe.dom.unfreeze());
            });
        }
    },
});
