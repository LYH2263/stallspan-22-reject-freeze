from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import inspect, text

from app.api.router import api_router
from app.config import settings
from app.database import Base, SessionLocal, engine
from app.services.seed import seed_if_empty


def _ensure_run_columns() -> None:
    """Idempotent additive migration for pre-existing allocation_runs tables."""
    insp = inspect(engine)
    if "allocation_runs" not in insp.get_table_names():
        return
    existing = {c["name"] for c in insp.get_columns("allocation_runs")}
    additions = {
        "geom_hash": "VARCHAR(64)",
        "geom_json": "TEXT",
        "summary": "TEXT",
        "summary_sig": "VARCHAR(80)",
    }
    with engine.begin() as conn:
        for name, ddl in additions.items():
            if name not in existing:
                conn.execute(text(f"ALTER TABLE allocation_runs ADD COLUMN {name} {ddl}"))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(bind=engine)
    _ensure_run_columns()
    if settings.seed_on_empty:
        db = SessionLocal()
        try:
            seed_if_empty(db)
        finally:
            db.close()
    yield


app = FastAPI(title="StallSpan", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(api_router, prefix="/api")
