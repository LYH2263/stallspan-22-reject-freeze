from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import Pillar
router = APIRouter(prefix="/pillars", tags=["pillars"])


class PillarIn(BaseModel):
    segment_id: int = 1
    position_m: float = Field(ge=0)
    thickness_m: float = Field(default=0.4, gt=0)
    label: str = "挡柱"


@router.get("")
def list_pillars(db: Session = Depends(get_db)):
    return [{"id": r.id, "segment_id": r.segment_id, "position_m": r.position_m,
             "thickness_m": r.thickness_m, "label": r.label}
            for r in db.scalars(select(Pillar).order_by(Pillar.position_m)).all()]


@router.post("", status_code=201)
def add_pillar(body: PillarIn, db: Session = Depends(get_db)):
    """改柱：新增挡柱只会改变此后确认的几何；历史 AllocationRun 一行都不动。"""
    p = Pillar(segment_id=body.segment_id, position_m=body.position_m,
               thickness_m=body.thickness_m, label=body.label)
    db.add(p); db.commit(); db.refresh(p)
    return {"id": p.id, "segment_id": p.segment_id, "position_m": p.position_m,
            "thickness_m": p.thickness_m, "label": p.label}


@router.delete("/{pillar_id}", status_code=204)
def remove_pillar(pillar_id: int, db: Session = Depends(get_db)):
    p = db.get(Pillar, pillar_id)
    if not p:
        raise HTTPException(404, "挡柱不存在")
    db.delete(p); db.commit()
