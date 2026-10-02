"""验收锚：确认时刻几何哈希固化；多口摘要逐字一致；改柱/外扩不改旧条；脏摘要不写回。"""
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models.models import AllocationRun, MarketDay, Pillar, Segment, Vendor
from app.services.first_fit_engine import (
    blocked_bands_from_pillars,
    build_summary,
    hash_geometry,
    normalized_geometry,
    sign_summary,
)


@pytest.fixture()
def SessionLocal():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(engine)
    db = TestingSession()
    day = MarketDay(name="周末夜市", day=date(2026, 9, 20))
    db.add(day); db.flush()
    seg = Segment(market_day_id=day.id, name="东街段", width_m=30.0)
    db.add(seg); db.flush()
    db.add(Pillar(segment_id=seg.id, position_m=10.0, thickness_m=0.5, label="灯柱A"))
    db.add(Pillar(segment_id=seg.id, position_m=20.0, thickness_m=0.5, label="灯柱B"))
    for name, wdt, pri in [
        ("阿强烧烤", 4.0, 1), ("林记糖水", 3.0, 1), ("老周水果", 5.0, 2),
        ("小美饰品", 2.5, 2), ("大碗面", 6.0, 1), ("手作皮具", 3.5, 3),
        ("巨型舞台车", 12.0, 9),
    ]:
        db.add(Vendor(market_day_id=day.id, name=name, stall_width_m=wdt, priority=pri))
    db.commit(); db.close()

    def override_get_db():
        s = TestingSession()
        try:
            yield s
        finally:
            s.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestingSession
    app.dependency_overrides.clear()


@pytest.fixture()
def client(SessionLocal):
    return TestClient(app)


# ---------- 几何规范化 ----------

def test_normalized_geometry_is_order_and_overlap_stable():
    g1 = normalized_geometry(30.0, [
        {"position_m": 10.0, "thickness_m": 0.5},
        {"position_m": 20.0, "thickness_m": 0.5},
    ])
    g2 = normalized_geometry(30.0, [
        {"position_m": 20.0000001, "thickness_m": 0.5},
        {"position_m": 10.0, "thickness_m": 2.5},  # 9.75–11.25 与原 9.75–10.25 并集更大
        {"position_m": 10.0, "thickness_m": 0.5},
    ])
    # 顺序无关
    g3 = normalized_geometry(30.0, list(reversed([
        {"position_m": 10.0, "thickness_m": 0.5},
        {"position_m": 20.0, "thickness_m": 0.5},
    ])))
    assert g1 == g3
    assert hash_geometry(g1) == hash_geometry(g3)
    # 重叠/相接带必须并入并集；几何不同哈希必分叉
    bands = blocked_bands_from_pillars(30.0, [
        {"position_m": 10.0, "thickness_m": 1.0},
        {"position_m": 10.4, "thickness_m": 1.0},
    ])
    assert bands == [(9.5, 10.9)]
    assert hash_geometry(g1) != hash_geometry(g2)


def test_hash_changes_on_pillar_move_and_widen():
    base = hash_geometry(normalized_geometry(30.0, [{"position_m": 10.0, "thickness_m": 0.5}]))
    moved = hash_geometry(normalized_geometry(30.0, [{"position_m": 11.0, "thickness_m": 0.5}]))
    widened = hash_geometry(normalized_geometry(32.0, [{"position_m": 10.0, "thickness_m": 0.5}]))
    assert base != moved
    assert base != widened


# ---------- 确认即固化 ----------

def test_confirm_pins_geometry_hash_and_summary(client, SessionLocal):
    res = client.post("/api/allocate/run?segment_id=1")
    assert res.status_code == 200
    body = res.json()
    db = SessionLocal()
    run = db.get(AllocationRun, body["id"])
    expected_hash = hash_geometry(normalized_geometry(30.0, [
        {"position_m": 10.0, "thickness_m": 0.5},
        {"position_m": 20.0, "thickness_m": 0.5},
    ]))
    assert run.geom_hash == expected_hash == body["geom_hash"]
    assert run.summary is not None and run.summary_sig is not None
    assert body["summary"] == run.summary
    assert body["geometry_drift"] is False
    assert body["summary_dirty"] is False
    db.close()


def test_three_read_ports_return_verbatim_same_summary(client):
    run = client.post("/api/allocate/run?segment_id=1").json()
    latest = client.get("/api/allocate/latest?segment_id=1").json()
    drawer = client.get("/api/allocate/runs?segment_id=1").json()
    detail = client.get(f"/api/allocate/runs/{run['id']}?segment_id=1").json()
    assert latest["summary"] == run["summary"]
    assert drawer[0]["summary"] == run["summary"]
    assert detail["summary"] == run["summary"]
    assert latest["geom_hash"] == detail["geom_hash"] == drawer[0]["geom_hash"]


def test_latest_is_readonly_when_no_run(client):
    assert client.get("/api/allocate/latest?segment_id=1").status_code == 404


# ---------- 改柱 / 外扩：旧条不改口 ----------

def test_pillar_change_flags_drift_but_keeps_old_summary_verbatim(client, SessionLocal):
    old = client.post("/api/allocate/run?segment_id=1").json()
    old_summary = old["summary"]

    add = client.post("/api/pillars", json={
        "segment_id": 1, "position_m": 15.0, "thickness_m": 0.6, "label": "新增灯柱",
    })
    assert add.status_code == 201

    latest = client.get("/api/allocate/latest?segment_id=1").json()
    drawer = client.get("/api/allocate/runs?segment_id=1").json()[0]
    detail = client.get(f"/api/allocate/runs/{old['id']}?segment_id=1").json()
    # 禁止按此刻挡柱现场重算改旧摘要
    assert latest["summary"] == old_summary
    assert drawer["summary"] == old_summary
    assert detail["summary"] == old_summary
    for b in (latest, drawer, detail):
        assert b["geometry_drift"] is True
        assert b["summary_dirty"] is False
    # 旧运行钉存的几何哈希不被新几何覆盖
    assert latest["geom_hash"] == old["geom_hash"]

    # 新确认写新摘要（哈希分叉）
    new = client.post("/api/allocate/run?segment_id=1").json()
    assert new["geom_hash"] != old["geom_hash"]
    assert new["summary"] != old_summary
    assert new["geometry_drift"] is False

    # 并排点开旧条不得改口
    old_detail = client.get(f"/api/allocate/runs/{old['id']}?segment_id=1").json()
    assert old_detail["summary"] == old_summary
    assert old_detail["geom_hash"] == old["geom_hash"]
    assert old_detail["geometry_drift"] is True
    db = SessionLocal()
    assert db.scalar(select(func.count()).select_from(AllocationRun)) == 2
    db.close()


def test_widen_flags_drift_and_old_run_untouched(client):
    old = client.post("/api/allocate/run?segment_id=1").json()
    assert client.patch("/api/segments/1", json={"width_m": 33.0}).status_code == 200
    detail = client.get(f"/api/allocate/runs/{old['id']}?segment_id=1").json()
    assert detail["geometry_drift"] is True
    assert detail["summary"] == old["summary"]
    assert detail["segment"]["width_m"] == 30.0  # 快照里的街段宽度也是当时的

    new = client.post("/api/allocate/run?segment_id=1").json()
    assert new["segment"]["width_m"] == 33.0
    assert new["geom_hash"] != old["geom_hash"]
    # 缩短被拒
    assert client.patch("/api/segments/1", json={"width_m": 10.0}).status_code == 422


# ---------- 脏摘要：截短后返回截短文本，绝不写回 ----------

def test_truncated_summary_stays_truncated_and_flags_dirty(client, SessionLocal):
    run = client.post("/api/allocate/run?segment_id=1").json()
    db = SessionLocal()
    row = db.get(AllocationRun, run["id"])
    row.summary = row.summary[:7]  # 模拟库内摘要被截短
    db.commit(); db.close()

    for path in ("/api/allocate/latest?segment_id=1",
                 "/api/allocate/runs?segment_id=1",
                 f"/api/allocate/runs/{run['id']}?segment_id=1"):
        body = client.get(path).json()
        item = body[0] if isinstance(body, list) else body
        assert item["summary"] == run["summary"][:7]
        assert item["summary_dirty"] is True
        # 签名断裂 → 几何锚不可信，漂移灯必须一并亮
        assert item["geometry_drift"] is True

    # 只读之后仍未被偷偷写回
    db = SessionLocal()
    assert db.get(AllocationRun, run["id"]).summary == run["summary"][:7]
    db.close()


# ---------- 原子性：不留半截运行 ----------

def test_failed_commit_leaves_no_half_run(client, SessionLocal, monkeypatch):
    import sqlalchemy.orm
    before = SessionLocal().scalar(select(func.count()).select_from(AllocationRun))

    def boom(self):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(sqlalchemy.orm.Session, "commit", boom)
    res = client.post("/api/allocate/run?segment_id=1")
    monkeypatch.undo()
    assert res.status_code == 500
    db = SessionLocal()
    after = db.scalar(select(func.count()).select_from(AllocationRun))
    db.close()
    assert after == before  # 行数不增于半截


def test_every_confirmed_run_has_hash_and_signature(client, SessionLocal):
    client.post("/api/allocate/run?segment_id=1")
    db = SessionLocal()
    for r in db.scalars(select(AllocationRun)).all():
        assert r.geom_hash and r.geom_json and r.summary and r.summary_sig
        # 自洽：签名对得上
        assert r.summary_sig == sign_summary(r.summary, r.geom_hash)
    db.close()


# ---------- 种子语义：巨型舞台车 ----------

def test_giant_stage_truck_rejection_keeps_seed_wording(client):
    body = client.post("/api/allocate/run?segment_id=1").json()
    rejected = {r["vendor_name"]: r for r in body["rejected"]}
    assert "巨型舞台车" in rejected
    assert rejected["巨型舞台车"]["reason"] == "无连续空档可放下且不跨越挡柱"
    assert "巨型舞台车" in body["summary"]


def test_summary_is_verbatim_deterministic():
    r = {"placements": [1, 2], "rejected": [{"vendor_name": "巨型舞台车"}], "free_spans": []}
    h = "abc123"
    assert build_summary(r, h) == build_summary(r, h)
    assert build_summary(r, h) != build_summary(r, "other")
