"""Roles, pages, decisions and their defaults (ADR-0007).

Defaults live here; the database stores only the COO's changes.
"""

from enum import StrEnum


class Role(StrEnum):
    PLANT_DIRECTOR = "plant_director"
    COO = "coo"
    PLANNER = "planner"
    SHIFT_LEAD = "shift_lead"
    STATION = "station"
    IT = "it"


PAGES = (
    "run",
    "data",
    "main",
    "loss",
    "machines",
    "actions",
    "report",
    "planner",
    "buffer",
    "plan",
    "flow",
    "shift",
    "station",
    "value",
    "import",
    "setup",
    "calendar",
    "access",
    "users",
    "conn",
)
START_PAGE = {
    Role.PLANT_DIRECTOR: "main",
    Role.COO: "main",
    Role.PLANNER: "planner",
    Role.SHIFT_LEAD: "shift",
    Role.STATION: "station",
    Role.IT: "conn",
}


ROLE_MENUS: dict[Role, tuple[str, ...]] = {
    Role.PLANT_DIRECTOR: ("main", "loss", "actions", "plan", "value", "report"),
    Role.COO: PAGES,
    Role.PLANNER: (
        "planner",
        "buffer",
        "plan",
        "actions",
        "flow",
        "machines",
        "data",
        "run",
        "import",
        "setup",
        "calendar",
    ),
    Role.SHIFT_LEAD: ("shift", "flow", "buffer", "station"),
    Role.STATION: ("station",),
    Role.IT: ("conn", "users", "import", "data"),
}
"""Preset 'role menus only': each role opens just the pages it needs (mockup F3)."""


class Decision(StrEnum):
    ACCEPT_EXPLOIT_SUBORDINATE = "accept_exploit_subordinate"
    APPROVE_ELEVATE = "approve_elevate"
    RELEASE_EXPEDITE = "release_expedite"
    REPORT_STOP = "report_stop"
    EDIT_SETUP_CALENDAR = "edit_setup_calendar"
    IMPORT_RUN_DIAGNOSTIC = "import_run_diagnostic"
    FIX_ROWS = "fix_rows"
    DELETE_IMPORT = "delete_import"
    DELETE_PLANT_DATA = "delete_plant_data"
    SIGN_OFF_VALUE = "sign_off_value"
    MANAGE_LOGINS = "manage_logins"
    CHANGE_ACCESS = "change_access"


DEFAULT_DECISIONS: dict[Decision, frozenset[Role]] = {
    Decision.ACCEPT_EXPLOIT_SUBORDINATE: frozenset({Role.PLANT_DIRECTOR, Role.COO, Role.PLANNER}),
    Decision.APPROVE_ELEVATE: frozenset({Role.PLANT_DIRECTOR, Role.COO}),
    Decision.RELEASE_EXPEDITE: frozenset({Role.PLANNER, Role.SHIFT_LEAD}),
    Decision.REPORT_STOP: frozenset({Role.SHIFT_LEAD, Role.STATION}),
    Decision.EDIT_SETUP_CALENDAR: frozenset({Role.PLANNER, Role.IT}),
    Decision.IMPORT_RUN_DIAGNOSTIC: frozenset({Role.PLANNER, Role.IT}),
    Decision.FIX_ROWS: frozenset({Role.PLANNER, Role.IT}),
    Decision.DELETE_IMPORT: frozenset({Role.PLANNER, Role.IT}),
    Decision.DELETE_PLANT_DATA: frozenset({Role.IT}),
    Decision.SIGN_OFF_VALUE: frozenset({Role.PLANT_DIRECTOR, Role.COO}),
    Decision.MANAGE_LOGINS: frozenset({Role.IT}),
    Decision.CHANGE_ACCESS: frozenset({Role.COO}),
}
LOCKED_DECISIONS = {Decision.MANAGE_LOGINS: Role.IT, Decision.CHANGE_ACCESS: Role.COO}
"""Only IT manages logins and only the COO changes access; these cannot be reassigned."""

ROLE_LABEL = {
    Role.PLANT_DIRECTOR: "Plant director",
    Role.COO: "COO",
    Role.PLANNER: "Planner",
    Role.SHIFT_LEAD: "Shift lead",
    Role.STATION: "Station (operators)",
    Role.IT: "IT / ERP owner",
}
"""The role names the app shows (messages/en.json ``roles``), for refusals in plain words."""

DECISION_ACTION = {
    Decision.ACCEPT_EXPLOIT_SUBORDINATE: "accept or reject Exploit and Subordinate actions",
    Decision.APPROVE_ELEVATE: "approve Elevate actions",
    Decision.RELEASE_EXPEDITE: "release or expedite orders",
    Decision.REPORT_STOP: "report a stop",
    Decision.EDIT_SETUP_CALENDAR: "change the plant setup or calendar",
    Decision.IMPORT_RUN_DIAGNOSTIC: "upload or run imports",
    Decision.FIX_ROWS: "fix rows in the app",
    Decision.DELETE_IMPORT: "delete imports",
    Decision.DELETE_PLANT_DATA: "delete all data of a plant",
    Decision.SIGN_OFF_VALUE: "sign off measured value",
    Decision.MANAGE_LOGINS: "manage logins",
    Decision.CHANGE_ACCESS: "change access",
}
"""What a refusal says the role cannot do: 'Your role cannot delete imports.'"""


class Money(StrEnum):
    EUR = "eur"
    HOURS = "hours"


class Plants(StrEnum):
    ALL = "all"
    OWN = "own"
