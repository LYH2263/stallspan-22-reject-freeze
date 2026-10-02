from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Segment
router = APIRouter(prefix="/segments", tags=["segments"])


class SegmentPatch(BaseModel):
    width_m: float | None = None
    name: str | None = None


@router.get("")
def list_segments(db: Session = Depends(get_db)):
    return [{"id": r.id, "market_day_id": r.market_day_id, "name": r.name, "width_m": r.width_m}
            for r in db.scalars(select(Segment).order_by(Segment.id)).all()]


@router.patch("/{segment_id}")
def patch_segment(segment_id: int, body: SegmentPatch, db: Session = Depends(get_db)):
    seg = db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(404, "街段不存在")
    # Geometry edits never touch past runs; they only make the next confirmation diverge.
    if body.width_m is not None:
        if body.width_m <= 0:
            raise HTTPException(400, "宽度必须为正")
        seg.width_m = body.width_m
    if body.name is not None:
        seg.name = body.name
    db.commit()
    return {"id": seg.id, "market_day_id": seg.market_day_id, "name": seg.name,
            "width_m": seg.width_m}
