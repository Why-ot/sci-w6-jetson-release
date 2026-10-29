"""Measurement-eligibility gate for S40 (NEW code, this stage).

W6 (frozen) will happily compute a plane separation from any two ROIs. That is correct for a synthetic test
and dangerous for a real experiment: a separation number produced before the target is built, before the
reference is measured, or with an unfrozen ROI must never be reported as an S40 result.

This module is the gate that W6 does not have. It is deliberately a *separate* file in the new integration
directory; the frozen W6 source is not modified (see reports/W6_TRANSFER_INTEGRITY.md §5).
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Eligibility:
    """Everything that must be true before an S40 separation may be reported."""
    target_built: bool = False
    parallelism_deg: float | None = None          # measured, not nominal
    parallelism_tolerance_deg: float = 0.2
    reference_complete: bool = False              # 5x3 worksheet validated
    reference_u95_mm: float | str = "UNKNOWN"
    roi_frozen: bool = False
    roi_sha256: str | None = None
    intrinsics_from_device: bool = False
    depth_scale_from_device: bool = False
    min_valid_ratio: float = 0.90
    front_valid_ratio: float | None = None
    back_valid_ratio: float | None = None
    plane_rms_mm: float | None = None
    max_rms_mm: float = 0.2

    def reasons(self) -> list[str]:
        r = []
        if not self.target_built:
            r.append("S40 target not built / not verified")
        if self.parallelism_deg is None:
            r.append("parallelism not measured")
        elif self.parallelism_deg > self.parallelism_tolerance_deg:
            r.append(f"parallelism {self.parallelism_deg:.3f} deg exceeds "
                     f"{self.parallelism_tolerance_deg} deg tolerance")
        if not self.reference_complete:
            r.append("reference worksheet incomplete (needs 5 placements x 3 readings)")
        if self.reference_u95_mm == "UNKNOWN":
            r.append("reference U95 unknown")
        if not self.roi_frozen or not self.roi_sha256:
            r.append("ROI not frozen (no sha256 recorded)")
        if not self.intrinsics_from_device:
            r.append("intrinsics not read from the device")
        if not self.depth_scale_from_device:
            r.append("depth_scale not read from the device")
        for name, v in (("front", self.front_valid_ratio), ("back", self.back_valid_ratio)):
            if v is None:
                r.append(f"{name} ROI validity not measured")
            elif v < self.min_valid_ratio:
                r.append(f"{name} ROI valid ratio {v:.3f} < {self.min_valid_ratio}")
        if self.plane_rms_mm is None:
            r.append("plane fit RMS not measured")
        elif self.plane_rms_mm > self.max_rms_mm:
            r.append(f"plane RMS {self.plane_rms_mm:.3f} mm > {self.max_rms_mm} mm")
        return r

    @property
    def allowed(self) -> bool:
        return not self.reasons()

    def to_json(self) -> dict:
        d = self.__dict__.copy()
        d["allowed"] = self.allowed
        d["blocking_reasons"] = self.reasons()
        return d


def require_eligible(el: Eligibility) -> None:
    """Raise unless every precondition holds. Used before any reported separation."""
    if not el.allowed:
        raise PermissionError("S40 measurement not eligible: " + "; ".join(el.reasons()))


def from_session(session_dir: str | Path) -> Eligibility:
    """Best-effort gate built from an on-disk session, with nothing assumed."""
    p = Path(session_dir)
    el = Eligibility()
    ref = p / "placement_01" / "reference" / "reference_measurements.csv"
    if ref.exists():
        from w6.uncertainty import read_reference_rows, validate_reference_rows
        el.reference_complete = bool(validate_reference_rows(read_reference_rows(ref))["complete"])
    roi = p / "placement_01" / "meta" / "roi_definition.json"
    if roi.exists():
        try:
            d = json.loads(roi.read_text(encoding="utf-8"))
            el.roi_sha256 = d.get("_sha256")
            el.roi_frozen = bool(el.roi_sha256)
        except json.JSONDecodeError:
            pass
    dsf = p / "placement_01" / "meta" / "depth_scale.json"
    if dsf.exists():
        try:
            el.depth_scale_from_device = bool(json.loads(dsf.read_text()).get("depth_scale_m_per_unit"))
        except Exception:
            pass
    return el
