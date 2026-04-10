from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.paths import resolve_demo_static_root
from app.core.settings import settings


app = FastAPI(title=settings.app_name)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(router)

demo_static_root = resolve_demo_static_root()
demo_static_root.mkdir(parents=True, exist_ok=True)
app.mount("/demo/assets", StaticFiles(directory=str(demo_static_root)), name="demo-assets")


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/demo", status_code=307)


@app.get("/demo", include_in_schema=False)
def demo() -> FileResponse:
    return FileResponse(Path(demo_static_root) / "demo.html")
