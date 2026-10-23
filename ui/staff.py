"""Township staff screens: dashboard, assets, maintenance, complaints, risk, assistant and agent.

Each screen is a function that takes the app and returns a list of controls.
Business rules stay in services/intelligence/agent; these functions only present and forward actions.
"""
import flet as ft

import config as cfg
from intelligence.analytics import dashboard_metrics
from intelligence.assistant import TownshipAssistant
from intelligence.risk import assess_all
from intelligence.impact import impact_summary
from services import assets as asset_svc
from services import auth
from services import complaints as comp_svc
from services import maintenance as maint_svc
from services.errors import TownshipError
from ui.widgets import (
    CONDITION_COLORS, LEVEL_COLORS, STATUS_COLORS, URGENCY_COLORS, badge, card, dropdown, heading,
    metric, note, sample_banner, section_title, table,
)

EXAMPLE_QUESTIONS = [
    "Which assets need maintenance soon?",
    "Which assets have repeated repairs?",
    "What are the highest-risk assets and why?",
    "How much has been spent on drainage maintenance?",
    "Which complaints have remained open the longest?",
    "What should management prioritise this month?",
]
AGENT_EXAMPLES = [
    "show WP-001",
    "log complaint: water leaking at Block C, urgent",
    "record repair for WP-002: valve replaced, cost RM 350",
    "mark complaint 1 resolved",
    "overdue inspections",
    "dashboard summary",
]
ASSET_FIELDS = ["asset_code", "name", "asset_type", "location", "install_year", "lifespan_years",
                "condition", "last_inspection", "maintenance_interval_days", "notes"]


def _pick_asset(app, code):
    app.selected_asset = asset_svc.get_asset(app.conn, code)
    app.show_staff("Assets")


def _pick_complaint(app, complaint_id):
    app.selected_complaint = comp_svc.get_complaint(app.conn, complaint_id)
    app.show_staff("Complaints")


# ----- dashboard -----

def dashboard(app):
    m = dashboard_metrics(app.conn, app.today)
    recurring_rows = [
        (r.asset_code, [r.asset_code, r.name, r.repair_count, r.actions[0]]) for r in m["recurring"]
    ]
    recent_rows = [
        (i, [r["record_date"], r["asset_code"], r["name"], r["category"], r["description"],
             f"{r['cost_rm']:,.2f}", r["status"]])
        for i, r in enumerate(m["recent_records"])
    ]
    return [
        heading("Management dashboard"),
        sample_banner(),
        ft.Row([
            metric("Assets", m["total_assets"]),
            metric("Overdue inspections", len(m["overdue"]), ft.colors.RED_50),
            metric("Due within 30 days", len(m["upcoming"]), ft.colors.AMBER_50),
            metric("Open complaints", m["open_complaints"]),
            metric("Urgent open complaints", m["urgent_open_complaints"], ft.colors.ORANGE_50),
            metric("Recorded spend (RM)", f"{m['total_spend']:,.2f}"),
        ], wrap=True, spacing=10, run_spacing=10),
        section_title("Assets by risk level"),
        ft.Row([metric(level, count, LEVEL_COLORS[level]) for level, count in m["by_risk"].items()],
               wrap=True, spacing=10, run_spacing=10),
        section_title("Recurring defects and recommended actions"),
        table(["Asset", "Name", "Repairs (365 days)", "Recommended action"], recurring_rows,
              empty_text="No recurring repairs found."),
        section_title("Recent maintenance activity"),
        table(["Date", "Asset", "Name", "Category", "Description", "RM", "Status"], recent_rows),
    ]


# ----- assets -----

def assets(app):
    f = app.asset_filter

    def apply(_e=None):
        app.asset_filter = {"search": search.value or "", "type": type_dd.value or "All",
                            "condition": cond_dd.value or "All"}
        app.show_staff("Assets")

    search = ft.TextField(label="Search code, name or location (press Enter)", width=300,
                          value=f["search"], on_submit=apply)
    type_dd = dropdown("Asset type", ["All", *cfg.ASSET_TYPES], f["type"], on_change=apply)
    cond_dd = dropdown("Condition", ["All", *cfg.CONDITIONS], f["condition"], width=160, on_change=apply)

    rows = asset_svc.list_assets(
        app.conn, search=f["search"],
        asset_type="" if f["type"] == "All" else f["type"],
        condition="" if f["condition"] == "All" else f["condition"],
    )
    listing = table(
        ["Code", "Name", "Type", "Location", "Condition", "Last inspection", "Interval (days)"],
        [(r["asset_code"], [r["asset_code"], r["name"], r["asset_type"], r["location"],
                            badge(r["condition"], CONDITION_COLORS[r["condition"]]),
                            r["last_inspection"], r["maintenance_interval_days"]]) for r in rows],
        on_pick=lambda code: _pick_asset(app, code),
        empty_text="No assets match the filters.",
    )

    sel = app.selected_asset or {}
    today = app.today.isoformat()
    app.form = {
        "a_asset_code": ft.TextField(label="Asset code (e.g. WP-010)", width=200,
                                     value=sel.get("asset_code", ""), disabled=bool(sel)),
        "a_name": ft.TextField(label="Name", width=320, value=sel.get("name", "")),
        "a_asset_type": dropdown("Asset type", cfg.ASSET_TYPES, sel.get("asset_type", cfg.ASSET_TYPES[0])),
        "a_location": ft.TextField(label="Location", width=200, value=sel.get("location", "")),
        "a_install_year": ft.TextField(label="Installation year", width=160,
                                       value=str(sel.get("install_year", app.today.year - 5))),
        "a_lifespan_years": ft.TextField(label="Expected lifespan (years)", width=180,
                                         value=str(sel.get("lifespan_years", 30))),
        "a_condition": dropdown("Condition", cfg.CONDITIONS, sel.get("condition", "Good"), width=160),
        "a_last_inspection": ft.TextField(label="Last inspection (YYYY-MM-DD)", width=200,
                                          value=sel.get("last_inspection", today)),
        "a_maintenance_interval_days": ft.TextField(label="Maintenance interval (days)", width=200,
                                                    value=str(sel.get("maintenance_interval_days", 180))),
        "a_notes": ft.TextField(label="Notes", width=520, multiline=True, value=sel.get("notes", "")),
    }
    form_fields = list(app.form.values())
    return [
        heading("Infrastructure asset register"),
        sample_banner(),
        ft.Row([search, type_dd, cond_dd], wrap=True),
        note(f"{len(rows)} asset(s). Tap a row to view or edit it."),
        listing,
        ft.Divider(),
        card([
            section_title("Selected asset" if sel else "New asset"),
            ft.Row(form_fields[:4], wrap=True),
            ft.Row(form_fields[4:9], wrap=True),
            form_fields[9],
            ft.Row([
                ft.ElevatedButton("Add asset", icon=ft.icons.ADD, on_click=lambda e: _save_new_asset(app),
                                  disabled=bool(sel)),
                ft.ElevatedButton("Update selected", icon=ft.icons.SAVE,
                                  on_click=lambda e: _update_asset(app), disabled=not sel),
                ft.OutlinedButton("Delete selected", icon=ft.icons.DELETE_OUTLINE,
                                  on_click=lambda e: _delete_asset(app), disabled=not sel),
                ft.TextButton("Clear selection", on_click=lambda e: _clear_asset(app)),
            ], wrap=True),
        ], width=900),
    ]


def _asset_data(app):
    return {k: (app.form["a_" + k].value or "") for k in ASSET_FIELDS}


def _save_new_asset(app):
    def action():
        code = asset_svc.create_asset(app.conn, _asset_data(app))
        app.selected_asset = asset_svc.get_asset(app.conn, code)
    if app.run_safely(action, "Asset created."):
        app.show_staff("Assets")


def _update_asset(app):
    def action():
        code = app.selected_asset["asset_code"]
        asset_svc.update_asset(app.conn, code, _asset_data(app))
        app.selected_asset = asset_svc.get_asset(app.conn, code)
    if app.run_safely(action, "Asset updated."):
        app.show_staff("Assets")


def _delete_asset(app):
    code = app.selected_asset["asset_code"]

    def action():
        asset_svc.delete_asset(app.conn, code)
        app.selected_asset = None
    if app.run_safely(action, f"Asset {code} and its maintenance records were deleted."):
        app.show_staff("Assets")


def _clear_asset(app):
    app.selected_asset = None
    app.show_staff("Assets")


# ----- maintenance -----

def maintenance(app):
    asset_filter = app.maint_filter["asset"]
    records = maint_svc.list_records(app.conn, asset_filter or None)

    def apply(_e=None):
        app.maint_filter = {"asset": (asset_field.value or "").strip()}
        app.show_staff("Maintenance")

    asset_field = ft.TextField(label="Filter by asset code (press Enter)", width=240,
                               value=asset_filter, on_submit=apply)
    listing = table(
        ["Date", "Asset", "Name", "Category", "Description", "RM", "Status"],
        [(i, [r["record_date"], r["asset_code"], r["asset_name"], r["category"],
              r["description"], f"{r['cost_rm']:,.2f}", r["status"]]) for i, r in enumerate(records)],
        empty_text="No maintenance records match this filter.",
    )
    app.form = {
        "m_asset_code": ft.TextField(label="Asset code", width=160),
        "m_record_date": ft.TextField(label="Date (YYYY-MM-DD)", width=170, value=app.today.isoformat()),
        "m_category": dropdown("Category", cfg.RECORD_CATEGORIES, "Inspection", width=200),
        "m_description": ft.TextField(label="What was done or found", width=360),
        "m_cost_rm": ft.TextField(label="Cost (RM)", width=130, value="0"),
        "m_status": dropdown("Status", cfg.RECORD_STATUSES, "Completed", width=150),
    }
    fields = list(app.form.values())
    return [
        heading("Maintenance history"),
        sample_banner(),
        asset_field,
        listing,
        ft.Divider(),
        card([
            section_title("Add a maintenance or inspection record"),
            ft.Row(fields[:4], wrap=True),
            ft.Row(fields[4:], wrap=True),
            ft.ElevatedButton("Add record", icon=ft.icons.ADD, on_click=lambda e: _add_record(app)),
        ], width=900),
    ]


def _add_record(app):
    data = {k[2:]: (c.value or "") for k, c in app.form.items()}
    if app.run_safely(lambda: maint_svc.add_record(app.conn, data), "Maintenance record added."):
        app.show_staff("Maintenance")


# ----- complaints -----

def complaints(app):
    f = app.complaint_filter

    def apply(_e=None):
        app.complaint_filter = {"status": status_dd.value, "urgency": urgency_dd.value}
        app.show_staff("Complaints")

    status_dd = dropdown("Status", ["All", *cfg.COMPLAINT_STATUSES], f["status"], width=180, on_change=apply)
    urgency_dd = dropdown("Urgency", ["All", *cfg.URGENCIES], f["urgency"], width=160, on_change=apply)

    rows = comp_svc.list_complaints(
        app.conn,
        status="" if f["status"] == "All" else f["status"],
        urgency="" if f["urgency"] == "All" else f["urgency"],
    )
    listing = table(
        ["ID", "Title", "Location", "Category", "Reported", "Days open", "Urgency", "Status", "Assigned to"],
        [(r["id"], [r["id"], r["title"], r["location"], r["category"], r["date_reported"],
                    comp_svc.days_open(r, app.today) if comp_svc.is_open(r) else "-",
                    badge(r["urgency"], URGENCY_COLORS[r["urgency"]]),
                    badge(r["status"], STATUS_COLORS.get(r["status"], ft.colors.GREY_200)),
                    r["assigned_to"] or "-"]) for r in rows],
        on_pick=lambda cid: _pick_complaint(app, cid),
        empty_text="No complaints match the filters.",
    )
    controls = [
        heading("Complaints"),
        sample_banner(),
        ft.Row([status_dd, urgency_dd], wrap=True),
        listing,
        ft.Divider(),
    ]
    controls += _complaint_detail(app)
    controls += _new_complaint_form(app)
    return controls


def _complaint_detail(app):
    if not app.selected_complaint:
        return [note("Tap a complaint in the table to review, update or view its history.")]
    c = app.selected_complaint
    app.form.update({
        "c_status": dropdown("Status", cfg.COMPLAINT_STATUSES, c["status"], width=180),
        "c_urgency": dropdown("Urgency", cfg.URGENCIES, c["urgency"], width=160),
        "c_assigned": ft.TextField(label="Assigned to", width=220, value=c["assigned_to"]),
        "c_note": ft.TextField(label="Note for the history log", width=360),
    })
    history = comp_svc.complaint_history(app.conn, c["id"])
    history_text = "\n".join(
        f"{h['changed_at']}: {h['field']} {h['old_value']} -> {h['new_value']}"
        + (f" ({h['note']})" if h["note"] else "")
        for h in history
    ) or "No status changes recorded yet."
    return [card([
        section_title(f"Complaint #{c['id']}: {c['title']}"),
        ft.Text(c["description"] or "No description.", size=12),
        note(f"Reporter: {c['reporter_name'] or '-'}  Contact: {c['reporter_contact'] or '-'}  "
             f"Linked asset: {c['asset_code'] or '-'}"),
        ft.Row([app.form["c_status"], app.form["c_urgency"], app.form["c_assigned"], app.form["c_note"]],
               wrap=True),
        ft.Row([
            ft.ElevatedButton("Apply changes", icon=ft.icons.SAVE, on_click=lambda e: _apply_complaint(app)),
            ft.TextButton("Clear selection", on_click=lambda e: _clear_complaint(app)),
        ]),
        section_title("Status history"),
        ft.Text(history_text, size=12, selectable=True),
        note("AI suggestions are never applied automatically. Staff decide all changes."),
    ], width=900)]


def _apply_complaint(app):
    changes = {"status": app.form["c_status"].value, "urgency": app.form["c_urgency"].value,
               "assigned_to": app.form["c_assigned"].value or ""}
    cid = app.selected_complaint["id"]
    note_text = app.form["c_note"].value or ""

    def action():
        app.selected_complaint = comp_svc.update_complaint(app.conn, cid, changes, note_text)
    if app.run_safely(action, "Complaint updated."):
        app.show_staff("Complaints")


def _clear_complaint(app):
    app.selected_complaint = None
    app.show_staff("Complaints")


def _new_complaint_form(app):
    app.form.update({
        "n_title": ft.TextField(label="Title", width=260),
        "n_description": ft.TextField(label="Description", width=400, multiline=True),
        "n_location": ft.TextField(label="Location", width=200),
        "n_category": dropdown("Category", cfg.ASSET_TYPES, cfg.ASSET_TYPES[-1], width=160),
        "n_urgency": dropdown("Urgency", cfg.URGENCIES, "Medium", width=140),
        "n_reporter_name": ft.TextField(label="Reporter name (optional)", width=200),
        "n_reporter_contact": ft.TextField(label="Contact (optional)", width=200),
        "n_asset_code": ft.TextField(label="Linked asset code (optional)", width=200),
    })
    fields = [app.form[k] for k in ("n_title", "n_description", "n_location", "n_category", "n_urgency",
                                    "n_reporter_name", "n_reporter_contact", "n_asset_code")]
    return [card([
        section_title("Log a new complaint"),
        ft.Row(fields[:4], wrap=True),
        ft.Row(fields[4:], wrap=True),
        ft.ElevatedButton("Submit complaint", icon=ft.icons.SEND, on_click=lambda e: _submit_complaint(app)),
    ], width=900)]


def _submit_complaint(app):
    data = {k[2:]: (c.value or "") for k, c in app.form.items() if k.startswith("n_")}
    data["date_reported"] = app.today.isoformat()
    if app.run_safely(lambda: comp_svc.create_complaint(app.conn, data), "Complaint logged."):
        app.show_staff("Complaints")


# ----- risk insights -----

def risk(app):
    risks = assess_all(app.conn, app.today)
    rows = [(r.asset_code, [r.asset_code, r.name, f"{r.score}/100",
                            badge(r.level, LEVEL_COLORS[r.level]), f"{r.lifespan_used_pct}%",
                            r.next_due, r.repair_count, " ".join(r.reasons), " ".join(r.actions)])
            for r in risks]
    return [
        heading("Risk and maintenance insights"),
        sample_banner(),
        note("Rule-based scores from transparent weights in config.py. These are not trained predictions. "
             "Age alone does not prove an asset will fail. Maintenance decisions remain with management."),
        table(["Asset", "Name", "Score", "Level", "Lifespan used", "Next inspection", "Repairs (365d)",
               "Reasons", "Suggested actions"], rows),
    ]


# ----- assistant (questions) -----

def assistant(app):
    state = app.assistant_state
    field = ft.TextField(label="Ask about the township records", width=620, value=state["question"],
                         on_submit=lambda e: _ask(app, field.value))
    controls = [
        heading("Township intelligence assistant"),
        sample_banner(),
        ft.Row([field, ft.ElevatedButton("Ask", on_click=lambda e: _ask(app, field.value))]),
        ft.Row([ft.OutlinedButton(q, on_click=lambda e, q=q: _ask(app, q)) for q in EXAMPLE_QUESTIONS], wrap=True),
    ]
    result = state["result"]
    if result:
        controls.append(card([
            ft.Text(f"Q: {state['question']}", weight=ft.FontWeight.BOLD),
            ft.Text(result["answer"], selectable=True),
            note("Sources: " + ("; ".join(result["sources"]) if result["sources"] else "none")),
            note(f"Engine: {result['engine']}"),
        ], color=ft.colors.BLUE_GREY_50, width=900))
    return controls


def _ask(app, question):
    app.assistant_state["question"] = question or ""
    app.assistant_state["result"] = TownshipAssistant(app.conn, today=app.today).ask(question or "")
    app.show_staff("Assistant")


# ----- agent (tasks) -----

def agent_screen(app):
    state = app.agent_state
    field = ft.TextField(label="Tell the agent what you need", width=680, value=state.get("request", ""),
                         on_submit=lambda e: _run_agent(app, field.value))
    controls = [
        heading("Township agent"),
        sample_banner(),
        note(app.agent.status_text()),
        ft.Row([field, ft.ElevatedButton("Send", icon=ft.icons.SEND, on_click=lambda e: _run_agent(app, field.value))]),
        ft.Row([ft.OutlinedButton(ex, on_click=lambda e, ex=ex: _run_agent(app, ex)) for ex in AGENT_EXAMPLES],
               wrap=True),
        note("Nothing is saved until you press Confirm. Every proposal and decision is written to the audit log."),
    ]
    reply = state.get("reply")
    if reply:
        body = [
            note(f"Answered by: {'Claude model' if reply.mode == 'model' else 'Local planner'}"),
            ft.Text(reply.message, selectable=True),
        ]
        if reply.sources:
            body.append(note("Sources: " + "; ".join(reply.sources)))
        if reply.notice:
            body.append(ft.Text(reply.notice, size=12, color=ft.colors.ORANGE_800))
        body += _proposal_controls(app, reply.pending)
        controls.append(card(body, color=ft.colors.BLUE_GREY_50, width=900))
    return controls


def _run_agent(app, request):
    app.agent_state["request"] = request or ""
    app.agent_state["reply"] = app.agent.handle(request or "")
    app.show_staff("Agent")


def _proposal_controls(app, proposals):
    out = []
    for p in proposals:
        if p.status == "pending":
            out.append(card([
                section_title("Proposed change"),
                ft.Text(p.preview, selectable=True),
                ft.Row([
                    ft.ElevatedButton("Confirm", icon=ft.icons.CHECK, on_click=_confirm_handler(app, p.id)),
                    ft.TextButton("Cancel", on_click=_cancel_handler(app, p.id)),
                ]),
            ], color=ft.colors.WHITE))
        else:
            out.append(ft.Text(f"Proposal {p.status}: {p.result}", weight=ft.FontWeight.BOLD))
    return out


def _confirm_handler(app, proposal_id):
    def handler(e):
        try:
            proposal = app.agent.confirm(proposal_id)
            app.toast(proposal.result, error=proposal.status != "done")
        except TownshipError as exc:
            app.toast(str(exc), error=True)
        app.show_staff("Agent")
    return handler


def _cancel_handler(app, proposal_id):
    def handler(e):
        try:
            app.agent.cancel(proposal_id)
            app.toast("Proposal cancelled.")
        except TownshipError as exc:
            app.toast(str(exc), error=True)
        app.show_staff("Agent")
    return handler


# ----- sign-in gate -----

MAX_PIN_ATTEMPTS = 5


def gate(app):
    """Shown until the correct staff PIN is entered. The first use asks the user to set a PIN."""
    if not auth.pin_is_set(app.conn):
        new_pin = ft.TextField(label="Choose a staff PIN (at least 6 characters)", password=True,
                               can_reveal_password=True, width=320)
        confirm = ft.TextField(label="Type the PIN again", password=True, width=320)

        def set_pin(_e=None):
            if new_pin.value != confirm.value:
                app.toast("The two PINs do not match.", error=True)
                return
            if app.run_safely(lambda: auth.set_staff_pin(app.conn, new_pin.value), "Staff PIN saved."):
                app.unlock_staff()

        confirm.on_submit = set_pin
        return [card([
            heading("Set up staff access", 20),
            note("No staff PIN has been set yet. Choose one now and keep it safe."),
            new_pin, confirm,
            ft.ElevatedButton("Save PIN and continue", icon=ft.icons.LOCK_OPEN, on_click=set_pin),
        ], width=420)]

    pin = ft.TextField(label="Staff PIN", password=True, can_reveal_password=True, width=320)

    def unlock(_e=None):
        if app.failed_pin_attempts >= MAX_PIN_ATTEMPTS:
            app.toast("Too many wrong attempts. Restart the app to try again.", error=True)
            return
        if auth.verify_staff_pin(app.conn, pin.value):
            app.unlock_staff()
        else:
            app.failed_pin_attempts += 1
            left = MAX_PIN_ATTEMPTS - app.failed_pin_attempts
            app.toast(f"Wrong PIN. {left} attempt(s) left." if left else "Too many wrong attempts.", error=True)

    pin.on_submit = unlock
    return [card([
        heading("Township staff sign-in", 20),
        note("Enter the staff PIN to continue."),
        pin,
        ft.ElevatedButton("Unlock", icon=ft.icons.LOCK_OPEN, on_click=unlock),
    ], width=420)]


# ----- impact (estimates, with assumptions shown) -----

def impact(app):
    s = impact_summary(app.conn, app.today)
    return [
        heading("Impact estimates"),
        sample_banner(),
        note("These are estimates from the sample records and stated assumptions. They are not measured results. "
             "The pilot will replace them with real figures."),
        section_title("Preventive maintenance"),
        ft.Row([
            metric("Overdue inspections", s["overdue_inspections"], ft.colors.RED_50),
            metric("High or critical risk assets", s["high_risk_assets"], ft.colors.ORANGE_50),
            metric("Assets with repeated repairs", s["recurring_defect_assets"]),
        ], wrap=True, spacing=10, run_spacing=10),
        section_title("Money"),
        ft.Row([
            metric("Repeat-repair spend, last 365 days (RM)", f"{s['repeat_repair_spend_rm']:,.2f}"),
            metric("Estimated avoidable spend (RM)", f"{s['estimated_avoidable_spend_rm']:,.2f}", ft.colors.GREEN_50),
            metric("Estimated complaint handling cost (RM)", f"{s['estimated_complaint_handling_cost_rm']:,.2f}"),
        ], wrap=True, spacing=10, run_spacing=10),
        section_title("Resident complaints"),
        ft.Row([
            metric("Open complaints", s["open_complaints"]),
            metric("Average days open", s["avg_open_complaint_days"]),
            metric("Oldest open (days)", s["oldest_open_complaint_days"], ft.colors.AMBER_50),
        ], wrap=True, spacing=10, run_spacing=10),
        section_title("Assumptions"),
        card([ft.Text(a) for a in s["assumptions"]], width=900),
    ]


VIEWS = {
    "Impact": impact,
    "Dashboard": dashboard,
    "Assets": assets,
    "Maintenance": maintenance,
    "Complaints": complaints,
    "Risk insights": risk,
    "Assistant": assistant,
    "Agent": agent_screen,
}
