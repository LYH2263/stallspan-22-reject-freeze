"""验收锚：几何哈希固化 + 逐字摘要冻结。

覆盖需求中的每条不变式：
- 确认时钉住当时禁入带并集的规范化几何哈希；
- 运行抽屉/只读接口/放不下旁注读到的摘要逐字相同，分叉即废；
- 改柱或外扩后，旧运行摘要不被新几何覆盖，新确认另写新行；
- 库内摘要被截短后，入口仍返回截短文本并亮 summary_truncated，绝不偷偷写回；
- 确认失败不得留下哈希缺失的半截运行，行数不增；
- 巨型舞台车拒因措辞保持种子语义。
"""
from app.services.first_fit_engine import (
    geometry_hash,
    normalized_blocked,
    summary_anchor,
)

SEED_REASON = "无连续空档可放下且不跨越挡柱"


# ---------------------------------------------------------------- 引擎：规范化并集

def test_normalized_blocked_is_union_and_order_independent():
    a = normalized_blocked(30.0, [
        {"position_m": 10.0, "thickness_m": 0.5},
        {"position_m": 20.0, "thickness_m": 0.5},
    ])
    b = normalized_blocked(30.0, [
        {"position_m": 20.0, "thickness_m": 0.5},
        {"position_m": 10.0, "thickness_m": 0.5},
    ])
    assert a == [(9.75, 10.25), (19.75, 20.25)]
    assert a == b  # 顺序无关


def test_touching_pillars_merge_into_one_band():
    merged = normalized_blocked(30.0, [
        {"position_m": 9.9, "thickness_m": 0.4},
        {"position_m": 10.2, "thickness_m": 0.4},
    ])
    assert len(merged) == 1
    assert merged == [(9.7, 10.4)]
    # 同一并集几何必须得到同一哈希
    assert geometry_hash(30.0, merged) == geometry_hash(30.0, list(reversed(merged)))


def test_bands_clamped_to_segment():
    # 柱完全落在街段之外：夹取后无剩余区间
    assert normalized_blocked(5.0, [{"position_m": 10.0, "thickness_m": 4.0}]) == []
    # 柱压住起点：[-1.5, 1.5] 夹取为 [0, 1.5]
    assert normalized_blocked(5.0, [{"position_m": 0.0, "thickness_m": 3.0}]) == [(0.0, 1.5)]
    # 柱压住终点：[3, 6] 夹取为 [3, 5]
    assert normalized_blocked(5.0, [{"position_m": 4.5, "thickness_m": 3.0}]) == [(3.0, 5.0)]


# ---------------------------------------------------------------- 确认：哈希+摘要固化

def test_confirm_pins_hash_and_verbatim_summary(client, seed):
    r = client.post("/api/allocate/run?segment_id=1")
    assert r.status_code == 200
    body = r.json()
    assert body["geometry_hash"].startswith("sha256:")
    assert body["summary"].endswith(summary_anchor(body["geometry_hash"]))
    assert body["summary_truncated"] is False
    assert body["geometry_drifted"] is False


def test_every_surface_serves_identical_summary(client, seed):
    """多口摘要分叉即废：run/latest/runs/runs/{id} 逐字相同。"""
    confirmed = client.post("/api/allocate/run?segment_id=1").json()

    latest = client.get("/api/allocate/latest?segment_id=1").json()
    runs = client.get("/api/allocate/runs?segment_id=1").json()
    by_id = client.get(f"/api/allocate/runs/{confirmed['id']}").json()

    expected_summary = confirmed["summary"]
    expected_hash = confirmed["geometry_hash"]
    for got in (latest, runs[0], by_id):
        assert got["summary"] == expected_summary
        assert got["geometry_hash"] == expected_hash


def test_giant_stage_truck_rejection_wording_kept(client, seed):
    body = client.post("/api/allocate/run?segment_id=1").json()
    rejected = {(x["vendor_name"]): x for x in body["rejected"]}
    assert "巨型舞台车" in rejected
    assert rejected["巨型舞台车"]["reason"] == SEED_REASON
    assert "巨型舞台车" in body["summary"]
    assert SEED_REASON in body["summary"]


# ---------------------------------------------------------------- 改柱 / 外扩：旧条不改口

def test_pillar_change_does_not_overwrite_old_run(client, seed):
    first = client.post("/api/allocate/run?segment_id=1").json()
    first_summary, first_hash = first["summary"], first["geometry_hash"]

    # 此刻移动挡柱（现场几何改变）
    pillar = client.get("/api/pillars?segment_id=1").json()[0]
    patched = client.patch(f"/api/pillars/{pillar['id']}", json={"position_m": 14.0})
    assert patched.status_code == 200

    old = client.get(f"/api/allocate/runs/{first['id']}").json()
    assert old["summary"] == first_summary          # 逐字不改口
    assert old["geometry_hash"] == first_hash
    assert old["geometry_drifted"] is True           # 亮：几何已漂移
    # 旧条冻结的场景仍是改柱前的挡柱位置
    assert {round(p["position_m"], 3) for p in old["pillars"]} == {10.0, 20.0}

    # 新确认写新摘要、新哈希，另起一行
    second = client.post("/api/allocate/run?segment_id=1").json()
    assert second["id"] != first["id"]
    assert second["geometry_hash"] != first_hash
    assert second["summary"] != first_summary
    assert second["geometry_drifted"] is False

    # 并排再点旧条，仍是旧文本
    old_again = client.get(f"/api/allocate/runs/{first['id']}").json()
    assert old_again["summary"] == first_summary
    assert old_again["geometry_drifted"] is True

    listing = client.get("/api/allocate/runs?segment_id=1").json()
    assert {r["id"] for r in listing} == {first["id"], second["id"]}


def test_segment_widening_does_not_overwrite_old_run(client, seed):
    first = client.post("/api/allocate/run?segment_id=1").json()
    first_summary, first_hash = first["summary"], first["geometry_hash"]

    r = client.patch("/api/segments/1", json={"width_m": 40.0})
    assert r.status_code == 200

    old = client.get(f"/api/allocate/runs/{first['id']}").json()
    assert old["summary"] == first_summary
    assert old["geometry_hash"] == first_hash
    assert old["geometry_drifted"] is True
    # 旧条冻结的街段宽度不随外扩改变
    assert old["segment"]["width_m"] == 30.0

    second = client.post("/api/allocate/run?segment_id=1").json()
    assert second["geometry_hash"] != first_hash
    assert second["segment"]["width_m"] == 40.0


# ---------------------------------------------------------------- 摘要截短：原样返回 + 亮灯 + 不回写

def test_truncated_summary_is_served_verbatim_and_never_rewritten(client, seed, session_factory):
    confirmed = client.post("/api/allocate/run?segment_id=1").json()
    rid = confirmed["id"]

    # 库内摘要被外部截短
    db = session_factory()
    from app.models.models import AllocationRun
    run = db.get(AllocationRun, rid)
    run.summary = run.summary[:18]   # 锚被削掉
    db.commit()
    db.close()

    for path in (f"/api/allocate/runs/{rid}", "/api/allocate/latest?segment_id=1",
                 "/api/allocate/runs?segment_id=1"):
        body = client.get(path).json()
        got = body[0] if isinstance(body, list) else body
        assert got["summary"] == confirmed["summary"][:18]   # 截短文本原样返回
        assert got["summary_truncated"] is True               # 亮灯
        assert got["geometry_hash"] == confirmed["geometry_hash"]

    # 反复读取后库里仍是截短文本：禁止偷偷写回修脏
    db = session_factory()
    assert db.get(AllocationRun, rid).summary == confirmed["summary"][:18]
    db.close()


# ---------------------------------------------------------------- 确认失败：不留半截

def test_failed_confirmation_leaves_no_half_run(client, seed, session_factory, monkeypatch):
    from sqlalchemy.orm import Session
    from app.models.models import AllocationRun
    from sqlalchemy import func, select

    db = session_factory()
    before = db.scalar(select(func.count()).select_from(AllocationRun))
    db.close()

    def boom(self):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(Session, "commit", boom)
    r = client.post("/api/allocate/run?segment_id=1")
    assert r.status_code == 500
    monkeypatch.undo()

    db = session_factory()
    after = db.scalar(select(func.count()).select_from(AllocationRun))
    db.close()
    assert after == before  # 行数不增于半截

    # 后续成功确认仍写出哈希齐全的完整行
    ok = client.post("/api/allocate/run?segment_id=1").json()
    assert ok["geometry_hash"].startswith("sha256:")
    assert ok["summary"].endswith(summary_anchor(ok["geometry_hash"]))
