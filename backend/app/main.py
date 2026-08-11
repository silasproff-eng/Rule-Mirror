import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import get_settings

CLIENT_SEGMENT = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]*")
RESERVED_ROUTES = {"api", "assets", "docs", "health", "openapi.json", "redoc"}
ROOT_STATIC_FILES = {"apple-touch-icon.png", "favicon-32.png", "rulemirror-logo.png"}
DEFAULT_WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"


def valid_client_route(path: str) -> bool:
    if not path:
        return True
    if path in {"terms.html", "privacy.html"} | ROOT_STATIC_FILES:
        return True
    segments = path.split("/")
    return segments[0] not in RESERVED_ROUTES and all(CLIENT_SEGMENT.fullmatch(value) for value in segments)


def create_app(web_dist: Path | None = None, environment: str | None = None) -> FastAPI:
    settings = get_settings()
    active_environment = environment or settings.environment
    dist = web_dist or DEFAULT_WEB_DIST
    application = FastAPI(title=settings.app_display_name, docs_url="/docs" if active_environment == "development" else None)
    application.add_middleware(CORSMiddleware, allow_origins=settings.allowed_origins, allow_credentials=True, allow_methods=["GET", "POST", "PUT", "DELETE"], allow_headers=["Authorization", "Content-Type"])
    application.include_router(router)

    @application.get("/health")
    def health():
        return {"status": "ok", "provider": settings.market_data_provider}

    @application.exception_handler(Exception)
    async def unexpected_error(request, error):
        if active_environment in {"development", "test"}:
            raise error
        return JSONResponse(status_code=500, content={"detail": {"code": "internal_error", "message": "The request could not be completed"}})

    assets = dist / "assets"
    if assets.is_dir():
        application.mount("/assets", StaticFiles(directory=assets), name="web-assets")

    @application.api_route("/{client_path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    async def web_client(client_path: str):
        if not valid_client_route(client_path):
            raise HTTPException(404, detail={"code": "not_found", "message": "Route was not found"})
        requested = dist / client_path if client_path else None
        if requested and requested.is_file() and requested.parent == dist:
            return FileResponse(requested)
        index = dist / "index.html"
        if not index.is_file():
            if active_environment == "test":
                raise HTTPException(404, detail={"code": "web_build_missing", "message": "RuleMirror web build is unavailable"})
            return JSONResponse(status_code=503, content={"detail": {"code": "web_build_missing", "message": "Run python3 scripts/run_local.py to build RuleMirror before serving it"}})
        return FileResponse(index)

    return application


app = create_app()
