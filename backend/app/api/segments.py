from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Segment
router = APIRouter(prefix="/segments", tags=["segments"])


class SegmentWiden(BaseModel):
    width_m: float = Field(gt=0)


@router.get("")
def list_segments(db: Session = Depends(get_db)):
    return [{"id": r.id, "market_day_id": r.market_day_id, "name": r.name, "width_m": r.width_m}
            for r in db.scalars(select(Segment).order_by(Segment.id)).all()]


@router.patch("/{segment_id}")
def widen_segment(segment_id: int, body: SegmentWiden, db: Session = Depends(get_db)):
    """外扩：只允许加宽，不回收旧空间；历史运行的钉存几何不被覆盖。"""
    seg = db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(404, "街段不存在")
    if body.width_m < seg.width_m:
        raise HTTPException(422, "外扩只能加宽，不能缩短街段")
    seg.width_m = body.width_m
    db.commit(); db.refresh(seg)
    return {"id": seg.id, "name": seg.name, "width_m": seg.width_m, "market_day_id": seg.market_day_id}
