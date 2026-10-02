import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import AllocationRun, Pillar, Segment, Vendor
from app.services.first_fit_engine import (
    allocate_on_geometry,
    build_summary,
    geometry_hash,
    normalized_blocked,
    result_to_dict,
    summary_is_intact,
)

router = APIRouter(prefix="/allocate", tags=["allocate"])


def _current_geometry(seg: Segment, db: Session):
    """Recompute the LIVE blocked-band geometry — for drift comparison only.

    Never feeds this back into a stored run's summary.
    """
    pillars = [{"position_m": p.position_m, "thickness_m": p.thickness_m}
               for p in db.scalars(select(Pillar).where(Pillar.segment_id == seg.id)
                                   .order_by(Pillar.id)).all()]
    blocked = normalized_blocked(seg.width_m, pillars)
    return blocked, geometry_hash(seg.width_m, blocked)


def _freeze(segment_id: int, db: Session) -> AllocationRun:
    """Confirm one run: pin the live geometry hash + verbatim summary atomically."""
    seg = db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(404, "街段不存在")

    pillar_rows = db.scalars(select(Pillar).where(Pillar.segment_id == segment_id)
                             .order_by(Pillar.id)).all()
    pillar_snapshot = [{"id": p.id, "position_m": p.position_m,
                        "thickness_m": p.thickness_m, "label": p.label} for p in pillar_rows]
    blocked = normalized_blocked(seg.width_m, [
        {"position_m": p.position_m, "thickness_m": p.thickness_m} for p in pillar_rows])
    geom = geometry_hash(seg.width_m, blocked)

    vendors = [{"id": v.id, "name": v.name, "stall_width_m": v.stall_width_m, "priority": v.priority}
               for v in db.scalars(select(Vendor).where(Vendor.market_day_id == seg.market_day_id)
                                   .order_by(Vendor.id)).all()]
    result = result_to_dict(allocate_on_geometry(seg.width_m, vendors, blocked))
    result["segment"] = {"id": seg.id, "name": seg.name, "width_m": seg.width_m}
    result["pillars"] = pillar_snapshot  # frozen scene for side-by-side replay

    created = datetime.utcnow()
    summary = build_summary(seg.name, seg.width_m, blocked, geom, result,
                            created.strftime("%Y-%m-%d %H:%M:%S UTC"))

    run = AllocationRun(segment_id=segment_id, created_at=created,
                        result_json=json.dumps(result, ensure_ascii=False),
                        geometry_hash=geom, summary=summary)
    # Atomic: a confirmed row either exists with BOTH hash and summary, or not at all.
    # On failure roll back so no hash-less half-run lingers (row count never grows on failure).
    try:
        db.add(run)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "确认失败：未写入任何运行")
    db.refresh(run)
    return run


def _serialize(run: AllocationRun, live_hash: str) -> dict:
    """Serve stored text verbatim; flags are computed, never persisted back."""
    data = json.loads(run.result_json or "{}")
    pinned = run.geometry_hash or ""
    intact = summary_is_intact(run.summary, pinned)
    drifted = bool(pinned) and pinned != live_hash
    return {
        "id": run.id,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "geometry_hash": pinned,
        # The stored summary exactly as it lives in the DB — truncated text stays truncated.
        "summary": run.summary or "",
        "geometry_drifted": drifted,
        "summary_truncated": not intact,
        **data,
    }


@router.post("/run")
def run_allocate(segment_id: int = 1, db: Session = Depends(get_db)):
    seg = db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(404, "街段不存在")
    _, live_hash = _current_geometry(seg, db)
    run = _freeze(segment_id, db)
    return _serialize(run, live_hash)


@router.get("/latest")
def latest(segment_id: int = 1, db: Session = Depends(get_db)):
    seg = db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(404, "街段不存在")
    run = db.scalars(select(AllocationRun).where(AllocationRun.segment_id == segment_id)
                     .order_by(AllocationRun.id.desc())).first()
    if not run:
        # No history yet: first read confirms a fresh run rather than serving an ephemeral calc.
        run = _freeze(segment_id, db)
    _, live_hash = _current_geometry(seg, db)
    return _serialize(run, live_hash)


@router.get("/runs")
def list_runs(segment_id: int = 1, db: Session = Depends(get_db)):
    seg = db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(404, "街段不存在")
    _, live_hash = _current_geometry(seg, db)
    runs = db.scalars(select(AllocationRun).where(AllocationRun.segment_id == segment_id)
                      .order_by(AllocationRun.id.desc())).all()
    return [_serialize(r, live_hash) for r in runs]


@router.get("/runs/{run_id}")
def get_run(run_id: int, db: Session = Depends(get_db)):
    run = db.get(AllocationRun, run_id)
    if not run:
        raise HTTPException(404, "运行不存在")
    seg = db.get(Segment, run.segment_id)
    if not seg:
        raise HTTPException(404, "街段不存在")
    _, live_hash = _current_geometry(seg, db)
    return _serialize(run, live_hash)
