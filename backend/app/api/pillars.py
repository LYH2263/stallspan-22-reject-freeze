from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Pillar
router = APIRouter(prefix="/pillars", tags=["pillars"])


class PillarCreate(BaseModel):
    segment_id: int
    position_m: float
    thickness_m: float = 0.4
    label: str = "挡柱"


class PillarPatch(BaseModel):
    position_m: float | None = None
    thickness_m: float | None = None
    label: str | None = None


def _row(r: Pillar):
    return {"id": r.id, "segment_id": r.segment_id, "position_m": r.position_m,
            "thickness_m": r.thickness_m, "label": r.label}


@router.get("")
def list_pillars(segment_id: int | None = None, db: Session = Depends(get_db)):
    stmt = select(Pillar)
    if segment_id is not None:
        stmt = stmt.where(Pillar.segment_id == segment_id)
    return [_row(r) for r in db.scalars(stmt.order_by(Pillar.position_m)).all()]


@router.post("")
def create_pillar(body: PillarCreate, db: Session = Depends(get_db)):
    p = Pillar(segment_id=body.segment_id, position_m=body.position_m,
               thickness_m=body.thickness_m, label=body.label)
    db.add(p)
    db.commit()
    db.refresh(p)
    return _row(p)


@router.patch("/{pillar_id}")
def patch_pillar(pillar_id: int, body: PillarPatch, db: Session = Depends(get_db)):
    p = db.get(Pillar, pillar_id)
    if not p:
        raise HTTPException(404, "挡柱不存在")
    # Moving/changing a pillar never rewrites frozen run summaries or hashes.
    if body.position_m is not None:
        p.position_m = body.position_m
    if body.thickness_m is not None:
        if body.thickness_m < 0:
            raise HTTPException(400, "厚度不可为负")
        p.thickness_m = body.thickness_m
    if body.label is not None:
        p.label = body.label
    db.commit()
    return _row(p)
