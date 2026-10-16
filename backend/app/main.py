from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .database import Base, engine, migrate_schema
from .routers import compare, tasks

Base.metadata.create_all(bind=engine)
migrate_schema()

app = FastAPI(title="数据库对比工具", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(tasks.router)
app.include_router(compare.router)


@app.get("/api/health")
def health():
    return {"ok": True, "name": "database-comparison"}


def _web_dir() -> Path | None:
    here = Path(__file__).resolve()
    for path in (here.parents[2] / "web", here.parents[1] / "web"):
        if (path / "index.html").is_file():
            return path.resolve()
    return None


WEB_DIR = _web_dir()


if WEB_DIR is not None:

    @app.get("/", include_in_schema=False)
    def spa_index():
        return FileResponse(WEB_DIR / "index.html")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        root = WEB_DIR
        target = (root / full_path).resolve()
        if target.is_file() and root in target.parents:
            return FileResponse(target)
        return FileResponse(root / "index.html")
