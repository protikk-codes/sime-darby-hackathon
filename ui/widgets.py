"""Reusable UI building blocks. Presentation only, no database access."""
import flet as ft

from data.seed import SAMPLE_BANNER

LEVEL_COLORS = {
    "Low": ft.colors.GREEN_100,
    "Medium": ft.colors.AMBER_100,
    "High": ft.colors.ORANGE_200,
    "Critical": ft.colors.RED_200,
}
URGENCY_COLORS = LEVEL_COLORS
CONDITION_COLORS = {"Good": ft.colors.GREEN_100, "Fair": ft.colors.AMBER_100, "Poor": ft.colors.RED_200}
STATUS_COLORS = {
    "Open": ft.colors.BLUE_100,
    "Under review": ft.colors.PURPLE_100,
    "Assigned": ft.colors.TEAL_100,
    "In progress": ft.colors.AMBER_100,
    "Resolved": ft.colors.GREEN_100,
    "Closed": ft.colors.GREY_300,
}
RESIDENT_STATUS_TEXT = {
    "Open": "Received. Waiting to be looked at.",
    "Under review": "Our team is checking the problem.",
    "Assigned": "Passed to a work crew.",
    "In progress": "Work is under way.",
    "Resolved": "Marked as fixed. Tell us if it is still a problem.",
    "Closed": "This report is closed.",
}


def heading(text, size=22):
    return ft.Text(text, size=size, weight=ft.FontWeight.BOLD)


def section_title(text):
    return ft.Text(text, size=16, weight=ft.FontWeight.BOLD)


def note(text):
    return ft.Text(text, size=12, italic=True, color=ft.colors.GREY_700)


def sample_banner():
    return ft.Container(
        content=ft.Text(SAMPLE_BANNER, size=12, weight=ft.FontWeight.BOLD),
        bgcolor=ft.colors.AMBER_100, padding=8, border_radius=6,
    )


def badge(text, color):
    return ft.Container(
        content=ft.Text(str(text), size=12, weight=ft.FontWeight.BOLD),
        bgcolor=color, padding=ft.padding.symmetric(horizontal=10, vertical=4), border_radius=12,
    )


def metric(label, value, color=None):
    return ft.Container(
        content=ft.Column([
            ft.Text(str(value), size=24, weight=ft.FontWeight.BOLD),
            ft.Text(label, size=12),
        ], spacing=2),
        padding=14, border_radius=12, width=190,
        bgcolor=color or ft.colors.BLUE_GREY_50,
    )


def card(controls, color=None, on_click=None, width=None):
    return ft.Container(
        content=ft.Column(controls, spacing=8),
        padding=16, border_radius=12, width=width,
        bgcolor=color or ft.colors.WHITE,
        border=ft.border.all(1, ft.colors.BLUE_GREY_100),
        on_click=on_click, ink=on_click is not None,
    )


def table(headers, rows, on_pick=None, empty_text="Nothing to show yet."):
    """rows: list of (key, [values]). Values may be text or ready-made controls such as badges.
    on_pick(key) runs when a cell is tapped."""
    if not rows:
        return ft.Text(empty_text, italic=True)

    def make_tap(key):
        return lambda e: on_pick(key)

    data_rows = []
    for key, values in rows:
        cells = []
        for value in values:
            content = value if isinstance(value, ft.Control) else ft.Text(str(value), size=12)
            cells.append(ft.DataCell(content, on_tap=make_tap(key) if on_pick else None))
        data_rows.append(ft.DataRow(cells=cells))
    return ft.Row([ft.DataTable(
        columns=[ft.DataColumn(ft.Text(h, weight=ft.FontWeight.BOLD, size=12)) for h in headers],
        rows=data_rows, column_spacing=18, heading_row_height=40,
    )], scroll=ft.ScrollMode.AUTO)


def dropdown(label, options, value, width=200, on_change=None):
    return ft.Dropdown(
        label=label, width=width, value=value, on_change=on_change,
        options=[ft.dropdown.Option(o) for o in options],
    )
