"""1D First-Fit stall placement along a street segment; stalls cannot cross pillars.

A confirmation run freezes the *normalized blocked-band union geometry* at that
instant via a sha256 hash and a verbatim summary string. Read endpoints always
return the stored text byte-for-byte; they never recompute or rewrite history.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass

GEOMETRY_HASH_PREFIX = "sha256:"
SUMMARY_ANCHOR_PREFIX = "几何哈希："


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


def _q(x: float) -> float:
    """Canonical quantization for every geometric coordinate that gets hashed or printed."""
    return round(float(x), 3)


def normalized_blocked(width_m: float, pillars: list[dict]) -> list[tuple[float, float]]:
    """Union of pillar blocked intervals, clamped to [0, width], sorted and merged.

    Order/overlap of input pillars must not matter: two pillars at 9.8 and 10.0
    with touching thickness merge into one band just like reversed input.
    """
    width_m = float(width_m)
    raw: list[tuple[float, float]] = []
    for p in pillars:
        half = float(p.get("thickness_m", 0.4)) / 2.0
        lo = max(0.0, float(p["position_m"]) - half)
        hi = min(width_m, float(p["position_m"]) + half)
        if hi > lo:
            raw.append((lo, hi))
    raw.sort()
    merged: list[list[float]] = []
    for lo, hi in raw:
        if not merged or lo > merged[-1][1]:
            merged.append([lo, hi])
        else:
            merged[-1][1] = max(merged[-1][1], hi)
    return [(_q(a), _q(b)) for a, b in merged if _q(b) - _q(a) > 1e-9]


def free_spans_from_blocked(width_m: float, blocked: list[tuple[float, float]]) -> list[tuple[float, float]]:
    spans: list[tuple[float, float]] = []
    cursor = 0.0
    for lo, hi in blocked:
        if lo > cursor:
            spans.append((cursor, lo))
        cursor = hi
    if cursor < float(width_m):
        spans.append((cursor, float(width_m)))
    return [(_q(a), _q(b)) for a, b in spans if _q(b) - _q(a) > 1e-6]


def free_spans_from_pillars(width_m: float, pillars: list[dict]) -> list[tuple[float, float]]:
    """pillars: position_m, thickness_m — treated as blocked intervals."""
    return free_spans_from_blocked(width_m, normalized_blocked(width_m, pillars))


def geometry_hash(width_m: float, blocked: list[tuple[float, float]]) -> str:
    """Deterministic hash of the normalized blocked-band union geometry."""
    payload = f"{float(width_m):.3f}|" + ",".join(f"{a:.3f}-{b:.3f}" for a, b in blocked)
    return GEOMETRY_HASH_PREFIX + hashlib.sha256(payload.encode("utf-8")).hexdigest()


def allocate_on_geometry(width_m: float, vendors: list[dict],
                         blocked: list[tuple[float, float]]) -> AllocResult:
    """vendors sorted by priority ascending then id; each needs stall_width_m contiguous in one free span."""
    spans = free_spans_from_blocked(width_m, blocked)
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
                placements.append(Placement(v["id"], v["name"], _q(start), _q(end), need))
                span[0] = end
                placed = True
                break
        if not placed:
            rejected.append(Rejected(v["id"], v["name"], need, "无连续空档可放下且不跨越挡柱"))
    free = [(_q(a), _q(b)) for a, b in remain if b - a > 1e-6]
    return AllocResult(placements, rejected, free)


def allocate_first_fit(width_m: float, vendors: list[dict], pillars: list[dict]) -> AllocResult:
    """Convenience wrapper: normalize current pillars, then first-fit on the free spans."""
    blocked = normalized_blocked(width_m, pillars)
    return allocate_on_geometry(width_m, vendors, blocked)


def result_to_dict(r: AllocResult) -> dict:
    return {
        "placements": [asdict(p) for p in r.placements],
        "rejected": [asdict(x) for x in r.rejected],
        "free_spans": [{"start_m": a, "end_m": b} for a, b in r.free_spans],
    }


def build_summary(segment_name: str, width_m: float, blocked: list[tuple[float, float]],
                  geom_hash: str, result: dict, created_iso: str) -> str:
    """Render the ONE verbatim summary for a confirmed run.

    Every surface (run drawer, read endpoints, 放不下 sidebar) serves this exact
    stored string — nothing ever renders a per-endpoint re-derived copy.
    """
    lines = [
        "StallSpan 开间确认",
        f"街段 {segment_name} 宽{float(width_m):.3f}m",
        f"时刻 {created_iso}",
        f"几何 {geom_hash}",
        "禁入带 " + ("，".join(f"{a:.3f}-{b:.3f}" for a, b in blocked) or "无"),
        f"安置 {len(result.get('placements', []))} 摊",
    ]
    for p in result.get("placements", []):
        lines.append(
            f"{p['vendor_name']} {float(p['start_m']):.3f}-{float(p['end_m']):.3f}"
            f" 宽{float(p['width_m']):.3f}"
        )
    lines.append(f"放不下 {len(result.get('rejected', []))} 摊")
    for x in result.get("rejected", []):
        lines.append(f"{x['vendor_name']} 宽{float(x['width_m']):.3f} {x['reason']}")
    lines.append(SUMMARY_ANCHOR_PREFIX + geom_hash)
    return "\n".join(lines)


def summary_anchor(geom_hash: str) -> str:
    return SUMMARY_ANCHOR_PREFIX + geom_hash


def summary_is_intact(stored_summary: str | None, geom_hash: str | None) -> bool:
    """True only when the stored text still ends with the full pinned-hash anchor.

    A truncated/mangled summary fails this and must be surfaced verbatim with a
    warning flag — never silently rewritten from the live scene.
    """
    if not stored_summary or not geom_hash:
        return False
    return stored_summary.rstrip().endswith(summary_anchor(geom_hash))
