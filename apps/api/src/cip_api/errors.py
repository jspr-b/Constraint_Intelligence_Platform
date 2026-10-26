"""Every error the API returns: a stable ``code`` and a plain English ``message``.

The web shows ``message`` as it is and uses ``code`` to pick the next step (for example
``plant_not_found`` links to Plant setup). ``detail`` repeats the message for older clients.
No stack trace, exception name or SQL ever reaches the client; those go to the log.
"""

import logging
from http import HTTPStatus

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger("cip.api")

CATALOG: dict[str, tuple[int, str]] = {
    # Signing in
    "sign_in_required": (401, "Please sign in to continue."),
    "session_expired": (401, "Your session has ended. Please sign in again."),
    "dev_header_required": (401, "Dev mode: send the X-Tenant-Id header, or sign in."),
    "dev_header_invalid": (401, "Dev mode: the X-Tenant-Id or X-Role header is not valid."),
    "no_active_account": (
        401,
        "There is no active account for this email. Ask your IT / ERP owner to add you.",
    ),
    "station_not_recognised": (401, "This station or PIN is not recognised. Check and try again."),
    "company_sign_in_failed": (
        401,
        "Your company sign-in did not work. Try again, or ask your IT / ERP owner.",
    ),
    "station_login_off": (403, "This station login is switched off. Ask your IT / ERP owner."),
    # Access
    "own_plant_only": (403, "Your role sees its own plant only."),
    "page_not_allowed": (403, "Your role may not open this page. The COO decides access."),
    "decision_not_allowed": (403, "Your role cannot {action}. {who}."),
    "unknown_page": (422, "This page does not exist."),
    "page_locked": (409, "This page cannot be turned off for this role: it is its start page."),
    "decision_locked": (409, "This decision always stays with its role and cannot be moved."),
    # Plants and setup
    "plant_not_found": (404, "This plant does not exist (yet). Add it on Plant setup."),
    "plant_exists": (409, "A plant with this code already exists. Choose another code."),
    "unknown_plant": (422, "This plant does not exist. Add it on Plant setup first."),
    "unknown_station": (422, "This station does not exist for the plant."),
    "bad_step_code": (
        422,
        "Use your own short code for the step: capitals, digits and -, 2 to 32 characters, "
        "starting with a letter. A step is a place, so no words for people.",
    ),
    "unknown_machine": (
        422,
        "This machine does not exist for the plant. Machines come in with your import.",
    ),
    "machine_has_station_login": (
        409,
        "This machine has a station login. Your IT / ERP owner removes it first on Users.",
    ),
    # Calendar
    "break_not_found": (404, "This break no longer exists. The page will refresh."),
    "window_not_found": (404, "This calendar entry no longer exists. The page will refresh."),
    # Users
    "account_exists": (409, "An account with this email already exists."),
    "cannot_disable_self": (409, "You cannot switch off your own account."),
    "user_not_found": (404, "This account no longer exists. The page will refresh."),
    "station_login_exists": (409, "This machine already has a station login."),
    "station_login_not_found": (404, "This station login no longer exists. The page will refresh."),
    # Imports
    "import_not_changeable": (
        409,
        "This import was replaced or deleted, so its files cannot change. "
        "Change the version in use.",
    ),
    "file_not_found": (404, "This file is not part of the upload. The page will refresh."),
    "last_file": (
        422,
        "An upload needs at least one file. Add the right file first, then remove this one.",
    ),
    "correction_needs_import_in_use": (
        409,
        "Rows can be fixed only in an import that is in use. Open the import marked IN USE.",
    ),
    "correction_reason_required": (
        422,
        "Say why you fix this row, so everyone can see it later (for example: time typed wrong).",
    ),
    "line_not_found": (404, "Line {line} is not in {file}. The page will refresh."),
    "correction_personal_column": (
        422,
        "This is a personal column: it is never read, shown or fixed in the app.",
    ),
    "correction_column_not_found": (422, "Column {column} is not in {file}. Choose a column."),
    "correction_value_required": (422, "Type the right value, or choose to leave the row out."),
    "correction_still_rejected": (
        422,
        "The import still cannot read this value. It needs {rule}. Nothing was saved.",
    ),
    "removal_reason_required": (
        422,
        "This row came from an upload. Say why you remove it, so the next upload does not bring "
        "it back without a trace.",
    ),
    "step_has_touchpoints": (
        409,
        "This step has {count} touchpoints in the data in use, so removing it would change the "
        "answer without a trace. Leave its touchpoints out on the Import page first, or send a "
        "steps list without it.",
    ),
    "station_in_use": (409, "Steps still belong to this station. Move or remove them first."),
    "machine_not_found": (404, "This step is not in the plant. The page will refresh."),
    "station_not_found": (404, "This station is not in the plant. The page will refresh."),
    "correction_not_found": (404, "This correction no longer exists. The page will refresh."),
    "correction_already_undone": (409, "This correction was already undone."),
    "preview_after_run": (
        409,
        "This import already ran: its results show what it changed.",
    ),
    "import_not_found": (404, "This import no longer exists. The page will refresh."),
    "refresh_needs_import": (
        409,
        "This plant has no import in use, so there is nothing to calculate. Upload exports first.",
    ),
    "import_already_deleted": (409, "This import is already deleted. The page will refresh."),
    "facts_calculating": (
        409,
        "The numbers of this plant are being calculated. Wait until they are done (the page "
        "updates), then delete.",
    ),
    "plant_delete_confirm": (
        422,
        "Type the plant code {plant} exactly to confirm. Nothing was deleted.",
    ),
    "no_files": (422, "Choose at least one file to upload."),
    "no_table_files": (
        422,
        "None of these files is a table we can read. Upload CSV, TXT or Excel files, or a zip "
        "with them.",
    ),
    "table_not_found": (404, "That file or sheet is not in this upload. Reload the page."),
    "file_too_large": (
        413,
        "A file is larger than {limit_mb} MB. Split the export or ask support.",
    ),
    "import_running": (
        409,
        "An import for this plant is already running. Wait for it to finish; the page updates.",
    ),
    # Generic
    "invalid_input": (422, "Some fields are missing or in the wrong format: {fields}."),
    "not_found": (404, "This address does not exist."),
    "server_error": (
        500,
        "Something went wrong on our side. Nothing was changed. Try again; if it keeps happening, "
        "contact support.",
    ),
}


class ApiProblem(HTTPException):
    """Raise ``ApiProblem("plant_not_found")``; status and message come from the catalog."""

    def __init__(self, code: str, **values: object) -> None:
        status, message = CATALOG[code]
        self.code = code
        super().__init__(status, message.format(**values))


def _body(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message, "detail": message}


def _fields(exc: RequestValidationError) -> str:
    names = []
    for error in exc.errors():
        loc = [str(p) for p in error.get("loc", ()) if p not in ("body", "query", "path")]
        names.append(".".join(loc) or "request")
    return ", ".join(dict.fromkeys(names))


def install(app: FastAPI) -> None:
    """Register the handlers that turn every error into ``{code, message, detail}``."""

    @app.exception_handler(StarletteHTTPException)
    async def http_problem(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        if isinstance(exc, ApiProblem):
            code, message = exc.code, str(exc.detail)
        elif exc.status_code == 404:
            code, message = "not_found", CATALOG["not_found"][1]
        else:  # framework errors (405 and the like): plain phrase, no internals
            code = HTTPStatus(exc.status_code).phrase.lower().replace(" ", "_")
            message = f"{HTTPStatus(exc.status_code).phrase}."
        return JSONResponse(_body(code, message), exc.status_code, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def invalid_input(request: Request, exc: RequestValidationError) -> JSONResponse:
        message = CATALOG["invalid_input"][1].format(fields=_fields(exc))
        return JSONResponse(_body("invalid_input", message), 422)

    @app.exception_handler(Exception)
    async def server_error(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", extra={"path": request.url.path})
        return JSONResponse(_body("server_error", CATALOG["server_error"][1]), 500)
