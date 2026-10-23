"""TownshipOS shell: home screen, resident portal and staff portal.

Residents report problems and ask simple questions. Township staff manage the
records, complaints and agent. There is no login yet, so add one before real use.
"""
from datetime import date

import flet as ft

from agent.core import TownshipAgent
from services import auth
from services.errors import TownshipError
from ui import resident, staff
from ui.widgets import badge, heading, note

STAFF_SECTIONS = [
    ("Dashboard", ft.icons.DASHBOARD),
    ("Assets", ft.icons.INVENTORY_2),
    ("Maintenance", ft.icons.BUILD),
    ("Complaints", ft.icons.REPORT_PROBLEM),
    ("Risk insights", ft.icons.WARNING_AMBER),
    ("Impact", ft.icons.INSIGHTS),
    ("Assistant", ft.icons.HELP_OUTLINE),
    ("Agent", ft.icons.SMART_TOY),
]
RESIDENT_SECTIONS = [
    ("Report a problem", ft.icons.ADD_ALERT),
    ("My reports", ft.icons.LIST_ALT),
    ("Ask the assistant", ft.icons.CHAT),
]


class TownshipApp:
    def __init__(self, page, conn, today=None):
        self.page = page
        self.conn = conn
        self.today = today or date.today()
        self.agent = TownshipAgent(conn, today=self.today)           # staff: all tools
        self.resident_agent = TownshipAgent(conn, today=self.today)  # residents: questions only

        # Staff state
        self.selected_asset = None
        self.selected_complaint = None
        self.asset_filter = {"search": "", "type": "All", "condition": "All"}
        self.maint_filter = {"asset": ""}
        self.complaint_filter = {"status": "All", "urgency": "All"}
        self.assistant_state = {"question": "", "result": None}
        self.agent_state = {"request": "", "reply": None}
        self.form = {}
        self.staff_unlocked = False
        self.failed_pin_attempts = 0
        self.pending_staff_section = "Dashboard"

        # Resident state
        self.resident_state = {}
        self.resident_chat = []

        page.title = "TownshipOS"
        page.window_width = 1280
        page.window_height = 860
        page.padding = 16
        page.theme_mode = ft.ThemeMode.LIGHT
        self.body = ft.Column(expand=True)
        page.add(self.body)
        self.show_home()

    # ----- shared helpers -----

    def _set(self, controls):
        self.body.controls = controls
        self.page.update()

    def toast(self, message, error=False):
        self.page.snack_bar = ft.SnackBar(
            ft.Text(message),
            bgcolor=ft.colors.RED_100 if error else ft.colors.GREEN_100,
        )
        self.page.snack_bar.open = True
        self.page.update()

    def run_safely(self, action, success_message):
        """Run a write, show the outcome, and return True only if it worked."""
        try:
            action()
        except TownshipError as exc:
            self.toast(str(exc), error=True)
            return False
        except Exception as exc:  # last-resort guard so the window never crashes
            self.toast(f"Something went wrong: {exc}", error=True)
            return False
        self.toast(success_message)
        return True

    def _rail(self, sections, selected, handler):
        return ft.NavigationRail(
            selected_index=[name for name, _ in sections].index(selected),
            label_type=ft.NavigationRailLabelType.ALL,
            min_width=96,
            destinations=[ft.NavigationRailDestination(icon=icon, label=name) for name, icon in sections],
            on_change=lambda e: handler(sections[e.control.selected_index][0]),
        )

    def _shell(self, title, rail, content, right_badge=None):
        top = ft.Row([
            ft.TextButton("Home", icon=ft.icons.HOME, on_click=lambda e: self.show_home()),
            ft.Text(title, size=18, weight=ft.FontWeight.BOLD),
            ft.Container(expand=True),
            right_badge or ft.Container(),
        ], vertical_alignment=ft.CrossAxisAlignment.CENTER)
        main = ft.Row(
            [rail, ft.VerticalDivider(width=1),
             ft.Column(content, expand=True, scroll=ft.ScrollMode.AUTO)],
            expand=True, vertical_alignment=ft.CrossAxisAlignment.START,
        )
        return [top, ft.Divider(height=1), main]

    def agent_badge(self):
        provider = self.agent.provider
        if provider is None:
            return badge("Agent: local planner", ft.colors.BLUE_GREY_100)
        label = "Gemini" if "Gemini" in provider.name else "Claude"
        return badge(f"Agent: {label} ({provider.model})", ft.colors.TEAL_100)

    # ----- screens -----

    def show_home(self):
        def tile(title, text, icon, color, handler):
            return ft.Container(
                content=ft.Column([
                    ft.Icon(icon, size=40, color=ft.colors.BLUE_700),
                    ft.Text(title, size=18, weight=ft.FontWeight.BOLD),
                    ft.Text(text, size=13),
                ], spacing=8),
                width=300, padding=24, border_radius=16, bgcolor=color, ink=True,
                border=ft.border.all(1, ft.colors.BLUE_GREY_100), on_click=handler,
            )

        self._set([ft.Column([
            ft.Container(height=20),
            ft.Text("TownshipOS", size=36, weight=ft.FontWeight.BOLD),
            ft.Text("Township services, made simple.", size=16),
            ft.Container(height=20),
            ft.Row([
                tile("Report a problem", "Tell us about a broken pipe, blocked drain or faulty streetlight. "
                     "You get a reference number to track it.", ft.icons.ADD_ALERT, ft.colors.BLUE_50,
                     lambda e: self.show_resident("Report a problem")),
                tile("Ask a question", "Get quick answers about township services and how to report problems.",
                     ft.icons.CHAT, ft.colors.TEAL_50, lambda e: self.show_resident("Ask the assistant")),
                tile("Township staff", "Manage assets, maintenance, complaints, risk and the agent.",
                     ft.icons.ADMIN_PANEL_SETTINGS, ft.colors.BLUE_GREY_50,
                     lambda e: self.show_staff("Dashboard")),
            ], wrap=True, spacing=20, run_spacing=20),
        ], expand=True, scroll=ft.ScrollMode.AUTO)])

    def show_resident(self, section):
        rail = self._rail(RESIDENT_SECTIONS, section, self.show_resident)
        content = resident.VIEWS[section](self)
        self._set(self._shell("Resident services", rail, content))

    def show_staff(self, section):
        if not self.staff_unlocked:
            self.pending_staff_section = section
            self._set([ft.Row([ft.TextButton("Home", icon=ft.icons.HOME,
                                             on_click=lambda e: self.show_home())]),
                       ft.Divider(height=1)] + staff.gate(self))
            return
        rail = self._rail(STAFF_SECTIONS, section, self.show_staff)
        content = staff.VIEWS[section](self)
        lock = ft.TextButton("Lock", icon=ft.icons.LOCK, on_click=lambda e: self.lock_staff())
        right = ft.Row([self.agent_badge(), lock], spacing=8)
        self._set(self._shell("Township staff", rail, content, right))

    def unlock_staff(self):
        self.staff_unlocked = True
        self.failed_pin_attempts = 0
        self.show_staff(self.pending_staff_section)

    def lock_staff(self):
        self.staff_unlocked = False
        self.show_home()
