"""1D First-Fit stall placement along a street segment; stalls cannot cross pillars."""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import asdict, dataclass
from typing import Any

_QUANTUM = 1000  # geometry coordinates are millimetres; pillar union must be scale-stable


def _q(value: float) -> int:
    """Quantize to whole millimetres to absorb float wobble (10.0 vs 10.0000001)."""
    return int(round(float(value) * _QUANTUM))


def blocked_bands_from_pillars(width_m: float, pillars: list[dict]) -> list[tuple[float, float]]:
    """禁入带并集：挡柱投影到街上后合并相交/相接区间，裁进 [0, width]。"""
    width_q = _q(width_m)
    blocked: list[list[int]] = []
    for p in pillars:
        half = p.get("thickness_m", 0.4) / 2.0
        lo = max(0, _q(p["position_m"] - half))
        hi = min(width_q, _q(p["position_m"] + half))
        if hi > lo:
            blocked.append([lo, hi])
    blocked.sort()
    merged: list[list[int]] = []
    for lo, hi in blocked:
        if not merged or lo > merged[-1][1]:
            merged.append([lo, hi])
        else:
            merged[-1][1] = max(merged[-1][1], hi)
    return [(lo / _QUANTUM, hi / _QUANTUM) for lo, hi in merged]


def normalized_geometry(width_m: float, pillars: list[dict]) -> dict[str, Any]:
    """确认时刻固化的规范化几何：街段宽度 + 禁入带并集（已排序、已合并、毫米取整）。

    与输入顺序、重叠方式、浮点抖动无关；只取决于真实的禁入几何。
    """
    return {
        "width_m": _q(width_m) / _QUANTUM,
        "blocked_bands": [[lo, hi] for lo, hi in blocked_bands_from_pillars(width_m, pillars)],
    }


def canonical_geometry_json(geom: dict[str, Any]) -> str:
    return json.dumps(geom, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def hash_geometry(geom: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_geometry_json(geom).encode("utf-8")).hexdigest()[:16]


def build_summary(result: dict[str, Any], geom_hash: str) -> str:
    """放不下旁注摘要。同一结果 + 同一几何哈希 ⇒ 逐字相同；几何漂移 ⇒ 分叉。"""
    placements = result.get("placements", [])
    rejected = result.get("rejected", [])
    free = result.get("free_spans", [])
    names = "、".join(x.get("vendor_name", "") for x in rejected) or "无"
    return (
        f"几何{geom_hash}｜已安置{len(placements)}摊｜放不下{len(rejected)}摊（{names}）｜剩余空档{len(free)}段"
    )


_SUMMARY_SECRET = os.environ.get("STALLSPAN_SUMMARY_SECRET", "stallspan-runtime-summary")


def sign_summary(summary: str, geom_hash: str) -> str:
    return hmac.new(
        _SUMMARY_SECRET.encode("utf-8"),
        f"{geom_hash}\n{summary}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_summary(summary: str, geom_hash: str, sig: str | None) -> bool:
    """签名不符即脏：含库内被截短、被改写。缺签名的半截行同样判脏。"""
    if not sig:
        return False
    expect = sign_summary(summary, geom_hash)
    return hmac.compare_digest(expect, sig)

@dataclass
class Placement:
    vendor_id: int
    vendor_name: str
    start_m: float
    end_m: float
    width_m: float

@dataclass
class Rejected:
    vendor_id: int
    vendor_name: str
    width_m: float
    reason: str

@dataclass
class AllocResult:
    placements: list[Placement]
    rejected: list[Rejected]
    free_spans: list[tuple[float, float]]

def free_spans_from_pillars(width_m: float, pillars: list[dict]) -> list[tuple[float, float]]:
    """Complements of the normalized blocked-band union; allocation geometry == hashed geometry."""
    merged = blocked_bands_from_pillars(width_m, pillars)
    spans: list[tuple[int, int]] = []
    width_q = _q(width_m)
    cursor = 0
    for lo, hi in merged:
        lo_q, hi_q = _q(lo), _q(hi)
        if lo_q > cursor:
            spans.append((cursor, lo_q))
        cursor = hi_q
    if cursor < width_q:
        spans.append((cursor, width_q))
    return [(a / _QUANTUM, b / _QUANTUM) for a, b in spans if b - a > 0]

def allocate_first_fit(width_m: float, vendors: list[dict], pillars: list[dict]) -> AllocResult:
    """vendors sorted by priority ascending then id; each needs stall_width_m contiguous in one free span (no pillar cross)."""
    spans = free_spans_from_pillars(width_m, pillars)
    # mutable remaining capacity per span
    remain = [[a, b] for a, b in spans]
    ordered = sorted(vendors, key=lambda v: (v.get("priority", 1), v["id"]))
    placements: list[Placement] = []
    rejected: list[Rejected] = []
    for v in ordered:
        need = float(v["stall_width_m"])
        placed = False
        for span in remain:
            avail = span[1] - span[0]
            if avail + 1e-9 >= need:
                start = span[0]
                end = start + need
                placements.append(Placement(v["id"], v["name"], round(start, 3), round(end, 3), need))
                span[0] = end
                placed = True
                break
        if not placed:
            rejected.append(Rejected(v["id"], v["name"], need, "无连续空档可放下且不跨越挡柱"))
    free = [(round(a, 3), round(b, 3)) for a, b in remain if b - a > 1e-6]
    return AllocResult(placements, rejected, free)

def result_to_dict(r: AllocResult) -> dict:
    return {
        "placements": [asdict(p) for p in r.placements],
        "rejected": [asdict(x) for x in r.rejected],
        "free_spans": [{"start_m": a, "end_m": b} for a, b in r.free_spans],
    }
