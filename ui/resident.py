"""Resident portal: report a problem, follow reports, and ask simple questions."""
import flet as ft

import config as cfg
from services import assets as asset_svc
from services import complaints as comp_svc
from ui.widgets import RESIDENT_STATUS_TEXT, STATUS_COLORS, badge, card, dropdown, heading, note

URGENCY_CHOICES = {
    "Not urgent": "Low",
    "Needs fixing soon": "Medium",
    "Urgent": "High",
    "Immediate danger": "Critical",
}
NO_ASSET = "No specific asset"
ASK_EXAMPLES = [
    "How do I report a problem?",
    "What happens after I report a problem?",
    "How do I check the progress of my report?",
]


# ----- report a problem -----

def report(app):
    state = app.resident_state
    if state.get("submitted_id"):
        return [card([
            ft.Icon(ft.icons.CHECK_CIRCLE, size=48, color=ft.colors.GREEN_700),
            heading(f"Thank you. Your reference number is #{state['submitted_id']}.", 20),
            ft.Text("Keep this number. Use 'My reports' with the phone or email you gave "
                    "to see how your report is progressing."),
            ft.ElevatedButton("Report another problem", on_click=lambda e: _reset(app)),
        ], color=ft.colors.GREEN_50)]

    form = app.form
    form["r_title"] = ft.TextField(label="Short title, e.g. Water leaking on the pavement", width=520)
    form["r_description"] = ft.TextField(label="Describe what you see", multiline=True, min_lines=3,
                                         max_lines=6, width=520)
    form["r_location"] = ft.TextField(label="Where is it? (street, block or landmark)", width=520)
    form["r_category"] = dropdown("Type of problem", list(cfg.ASSET_TYPES), "Other", width=250)
    form["r_urgency"] = dropdown("How urgent is it?", list(URGENCY_CHOICES), "Needs fixing soon", width=250)
    asset_options = [NO_ASSET] + [f"{a['asset_code']} - {a['name']}" for a in asset_svc.list_assets(app.conn)]
    form["r_asset"] = dropdown("Nearby township asset (optional)", asset_options, NO_ASSET, width=520)
    form["r_name"] = ft.TextField(label="Your name (optional)", width=250)
    form["r_contact"] = ft.TextField(label="Phone or email, to check progress later (optional)", width=250)

    return [
        heading("Report a problem"),
        ft.Text("Tell us what you see. Our team reviews every report."),
        note("If someone is in immediate danger, call 999 first."),
        card([
            form["r_title"],
            form["r_description"],
            form["r_location"],
            ft.Row([form["r_category"], form["r_urgency"]], wrap=True),
            form["r_asset"],
            ft.Row([form["r_name"], form["r_contact"]], wrap=True),
            ft.ElevatedButton("Send report", icon=ft.icons.SEND, on_click=lambda e: _submit(app)),
        ], width=600),
    ]


def _reset(app):
    app.resident_state = {}
    app.show_resident("Report a problem")


def _submit(app):
    f = app.form
    chosen_asset = f["r_asset"].value or NO_ASSET
    data = {
        "title": f["r_title"].value or "",
        "description": f["r_description"].value or "",
        "location": f["r_location"].value or "",
        "category": f["r_category"].value or "",
        "urgency": URGENCY_CHOICES.get(f["r_urgency"].value or "", ""),
        "asset_code": chosen_asset.split(" - ")[0] if chosen_asset != NO_ASSET else "",
        "reporter_name": f["r_name"].value or "",
        "reporter_contact": f["r_contact"].value or "",
        "date_reported": app.today.isoformat(),
    }

    def action():
        new_id = comp_svc.create_complaint(app.conn, data)
        app.resident_state = {"submitted_id": new_id}

    if app.run_safely(action, "Report sent."):
        app.show_resident("Report a problem")


# ----- my reports -----

def my_reports(app):
    state = app.resident_state
    contact = ft.TextField(label="Phone or email you used when reporting", width=380,
                           value=state.get("lookup", ""))

    def lookup(_e=None):
        state["lookup"] = (contact.value or "").strip()
        app.show_resident("My reports")

    contact.on_submit = lookup
    rows = comp_svc.list_complaints_by_contact(app.conn, state.get("lookup", ""))

    controls = [
        heading("My reports"),
        note("Enter the contact you gave when reporting. This is a simple lookup, not a secure login."),
        ft.Row([contact, ft.ElevatedButton("Find my reports", icon=ft.icons.SEARCH, on_click=lookup)], wrap=True),
    ]
    if not state.get("lookup"):
        controls.append(ft.Text("Enter your contact above to see your reports."))
    elif not rows:
        controls.append(ft.Text("No reports found for that contact."))
    for r in rows:
        controls.append(card([
            ft.Row([
                ft.Text(f"#{r['id']} {r['title']}", weight=ft.FontWeight.BOLD, expand=True),
                badge(r["status"], STATUS_COLORS.get(r["status"], ft.colors.GREY_200)),
            ]),
            ft.Text(f"{r['location']}  ·  reported {r['date_reported']}", size=12),
            ft.Text(RESIDENT_STATUS_TEXT.get(r["status"], ""), size=14),
            ft.Text(f"Assigned to: {r['assigned_to']}", size=12) if r["assigned_to"] else ft.Container(),
        ], width=600))
    return controls


# ----- ask the assistant -----

def ask(app):
    chat = app.resident_chat
    field = ft.TextField(label="Type your question", width=480,
                         on_submit=lambda e: _send(app, field.value))
    bubbles = []
    if not chat:
        bubbles.append(note("Hi! Ask me about township services, or how to report a problem."))
    for who, text in chat[-30:]:
        is_you = who == "you"
        bubbles.append(ft.Row([ft.Container(
            content=ft.Text(text, selectable=True),
            bgcolor=ft.colors.BLUE_100 if is_you else ft.colors.GREY_100,
            padding=12, border_radius=12, width=420,
        )], alignment=ft.MainAxisAlignment.END if is_you else ft.MainAxisAlignment.START))

    return [
        heading("Ask the assistant"),
        ft.Column(bubbles, spacing=10),
        ft.Row([field, ft.ElevatedButton("Send", icon=ft.icons.SEND, on_click=lambda e: _send(app, field.value))]),
        ft.Row([ft.OutlinedButton(q, on_click=lambda e, q=q: _send(app, q)) for q in ASK_EXAMPLES], wrap=True),
        note("Answers come from township records. For a complaint, use 'Report a problem'."),
    ]


def _send(app, text):
    text = (text or "").strip()
    if not text:
        return
    app.resident_chat.append(("you", text))
    reply = app.resident_agent.handle(text, residents=True)
    app.resident_chat.append(("bot", reply.message))
    app.show_resident("Ask the assistant")


VIEWS = {
    "Report a problem": report,
    "My reports": my_reports,
    "Ask the assistant": ask,
}
