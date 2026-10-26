"""FastAPI service. Endpoints call the engine; the API never computes € or load figures itself."""

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
from redis import Redis
from sqlalchemy import create_engine, text

import constraint_engine.formulas
import constraint_engine.quality.report
import constraint_engine.reconstruct.capacity
import constraint_engine.reconstruct.durations  # noqa: F401  (registers task-time formulas)
from cip_api import errors
from cip_api.logging import configure_logging
from cip_api.settings import Settings, get_settings
from constraint_engine.formulas.registry import registry

log = logging.getLogger("cip.api")


def _check_db(settings: Settings) -> str:
    try:
        with create_engine(settings.db_url(), pool_pre_ping=True).connect() as conn:
            conn.execute(text("SELECT 1"))
        return "ok"
    except Exception:
        return "unreachable"


def _check_redis(settings: Settings) -> str:
    try:
        Redis(host=settings.redis_host, port=settings.redis_port, socket_timeout=1).ping()
        return "ok"
    except Exception:
        return "unreachable"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging()
    app = FastAPI(title="Constraint Intelligence API", version=settings.version)
    errors.install(app)

    @app.middleware("http")
    async def access_log(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        started = time.perf_counter()
        response = await call_next(request)
        log.info(
            "request",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                "request_id": str(uuid.uuid4()),
            },
        )
        return response

    @app.get("/health")
    def health() -> JSONResponse:
        checks = {"db": _check_db(settings), "redis": _check_redis(settings)}
        ok = all(v == "ok" for v in checks.values())
        return JSONResponse(
            {"status": "ok" if ok else "degraded", **checks}, status_code=200 if ok else 503
        )

    @app.get("/meta")
    def meta() -> dict[str, object]:
        return {
            "version": settings.version,
            "source_id": settings.source_id,
            "env": settings.env,
            "formulas": [
                {"formula_id": f.formula_id, "text": f.text, "unit": f.unit}
                for f in registry.list()
            ],
        }

    from cip_api.auth.access_routes import router as access_router
    from cip_api.auth.routes import router as auth_router
    from cip_api.auth.users import router as users_router
    from cip_api.calendar import router as calendar_router
    from cip_api.corrections import router as corrections_router
    from cip_api.data_quality import router as quality_router
    from cip_api.deletes import router as deletes_router
    from cip_api.detection import router as detection_router
    from cip_api.facts import router as facts_router
    from cip_api.imports import router as imports_router
    from cip_api.onboarding import router as onboarding_router
    from cip_api.plant_setup import router as setup_router
    from cip_api.plants import router as plants_router

    app.include_router(auth_router)
    app.include_router(users_router)
    app.include_router(access_router)
    app.include_router(plants_router)
    app.include_router(imports_router)
    app.include_router(corrections_router)
    app.include_router(deletes_router)
    app.include_router(setup_router)
    app.include_router(calendar_router)
    app.include_router(quality_router)
    app.include_router(onboarding_router)
    app.include_router(facts_router)
    app.include_router(detection_router)
    return app


app = create_app()
