import json
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.models import AllocationRun, Pillar, Segment, Vendor
from app.services.first_fit_engine import (
    allocate_first_fit,
    build_summary,
    hash_geometry,
    normalized_geometry,
    result_to_dict,
    sign_summary,
    verify_summary,
)
router = APIRouter(prefix="/allocate", tags=["allocate"])


def _load_geometry(segment_id: int, db: Session) -> tuple[Segment, list[dict], dict, str]:
    seg = db.get(Segment, segment_id)
    if not seg:
        raise HTTPException(404, "街段不存在")
    pillars = [
        {"position_m": p.position_m, "thickness_m": p.thickness_m}
        for p in db.scalars(
            select(Pillar).where(Pillar.segment_id == segment_id).order_by(Pillar.id)
        ).all()
    ]
    geom = normalized_geometry(seg.width_m, pillars)
    return seg, pillars, geom, hash_geometry(geom)


def _drift_flags(run: AllocationRun, current_geom_hash: str) -> tuple[bool, bool]:
    """摘要-几何签名断裂（库内被截短/改写）时，几何锚已不可信，漂移灯一并亮。"""
    dirty = not verify_summary(run.summary or "", run.geom_hash or "", run.summary_sig)
    drift = current_geom_hash != run.geom_hash or dirty
    return drift, dirty


def _serialize_run(run: AllocationRun, current_geom_hash: str) -> dict:
    """三口（latest / runs 抽屉 / run 详情）唯一出口：摘要逐字取库，绝不现场重算。"""
    data = json.loads(run.result_json or "{}")
    geometry_drift, summary_dirty = _drift_flags(run, current_geom_hash)
    return {
        "id": run.id,
        "created_at": run.created_at.isoformat() if run.created_at else None,
        "segment_id": run.segment_id,
        "geom_hash": run.geom_hash,
        "summary": run.summary,  # 逐字返回；即便已被截短也返回截短文本，不写回、不补全。
        "geometry_drift": geometry_drift,
        "summary_dirty": summary_dirty,
        **data,
    }


@router.post("/run")
def run_allocate(segment_id: int = 1, db: Session = Depends(get_db)):
    """确认一次新运行：把此刻挡柱禁入带并集的规范化几何哈希钉进该次运行。

    几何、哈希、摘要、签名一次原子写齐；任何一步失败整体回滚，不留哈希缺失的半截行。
    """
    seg, pillars, geom, geom_hash = _load_geometry(segment_id, db)
    vendors = [
        {"id": v.id, "name": v.name, "stall_width_m": v.stall_width_m, "priority": v.priority}
        for v in db.scalars(
            select(Vendor).where(Vendor.market_day_id == seg.market_day_id).order_by(Vendor.id)
        ).all()
    ]
    # 全部在事务外算好，避免算出一半再落库。
    result = result_to_dict(allocate_first_fit(seg.width_m, vendors, pillars))
    result["segment"] = {"id": seg.id, "name": seg.name, "width_m": seg.width_m}
    result["pillars"] = pillars
    summary = build_summary(result, geom_hash)
    sig = sign_summary(summary, geom_hash)
    run = AllocationRun(
        segment_id=segment_id,
        created_at=datetime.utcnow(),
        result_json=json.dumps(result, ensure_ascii=False),
        geom_hash=geom_hash,
        geom_json=json.dumps(geom, ensure_ascii=False, sort_keys=True),
        summary=summary,
        summary_sig=sig,
    )
    try:
        db.add(run)
        db.commit()
    except Exception:
        db.rollback()
        raise HTTPException(500, "运行固化失败，已回滚，未留下半截运行")
    db.refresh(run)
    return _serialize_run(run, geom_hash)


@router.get("/latest")
def latest(segment_id: int = 1, db: Session = Depends(get_db)):
    """只读：返回最近一次运行的存储快照；没有运行时不隐式创建。"""
    _, _, _, current_hash = _load_geometry(segment_id, db)
    run = db.scalars(
        select(AllocationRun)
        .where(AllocationRun.segment_id == segment_id)
        .order_by(AllocationRun.id.desc())
    ).first()
    if not run:
        raise HTTPException(404, "尚无已确认运行")
    return _serialize_run(run, current_hash)


@router.get("/runs")
def list_runs(segment_id: int = 1, db: Session = Depends(get_db)):
    """运行抽屉：历次运行的摘要列表，摘要与详情逐字同源。"""
    _, _, _, current_hash = _load_geometry(segment_id, db)
    runs = db.scalars(
        select(AllocationRun)
        .where(AllocationRun.segment_id == segment_id)
        .order_by(AllocationRun.id.desc())
    ).all()
    items = []
    for r in runs:
        drift, dirty = _drift_flags(r, current_hash)
        items.append({
            "id": r.id,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "geom_hash": r.geom_hash,
            "summary": r.summary,
            "geometry_drift": drift,
            "summary_dirty": dirty,
        })
    return items


@router.get("/runs/{run_id}")
def get_run(run_id: int, segment_id: int = 1, db: Session = Depends(get_db)):
    """只读详情：并排点开旧条时返回当时存储快照，旧摘要绝不改口。"""
    _, _, _, current_hash = _load_geometry(segment_id, db)
    run = db.get(AllocationRun, run_id)
    if not run or run.segment_id != segment_id:
        raise HTTPException(404, "运行不存在")
    return _serialize_run(run, current_hash)


@router.get("/geometry-hash")
def geometry_hash(segment_id: int = 1, db: Session = Depends(get_db)):
    """此刻（未确认）几何的哈希，供前端在确认前提示几何是否已变。"""
    _, _, geom, current_hash = _load_geometry(segment_id, db)
    return {"geom_hash": current_hash, "geometry": geom}
