"""Tests for the S40 measurement-eligibility gate (new code, this stage)."""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HERE / "w6_pkg" / "src"))
sys.path.insert(0, str(HERE / "integration"))

from eligibility import Eligibility, require_eligible            # noqa: E402


def complete() -> Eligibility:
    return Eligibility(target_built=True, parallelism_deg=0.1, reference_complete=True,
                       reference_u95_mm=0.6, roi_frozen=True, roi_sha256="ab" * 32,
                       intrinsics_from_device=True, depth_scale_from_device=True,
                       front_valid_ratio=0.97, back_valid_ratio=0.95, plane_rms_mm=0.05)


class TestEligibility(unittest.TestCase):
    def test_all_conditions_met_is_allowed(self):
        el = complete()
        self.assertTrue(el.allowed, el.reasons())
        require_eligible(el)                       # must not raise

    def test_default_is_refused(self):
        el = Eligibility()
        self.assertFalse(el.allowed)
        self.assertGreaterEqual(len(el.reasons()), 8)

    def test_each_missing_precondition_blocks(self):
        cases = {
            "target_built": dict(target_built=False),
            "parallelism": dict(parallelism_deg=None),
            "parallelism_tol": dict(parallelism_deg=0.5),
            "reference": dict(reference_complete=False),
            "u95": dict(reference_u95_mm="UNKNOWN"),
            "roi": dict(roi_frozen=False, roi_sha256=None),
            "intrinsics": dict(intrinsics_from_device=False),
            "scale": dict(depth_scale_from_device=False),
            "front_roi": dict(front_valid_ratio=0.5),
            "rms": dict(plane_rms_mm=0.9),
        }
        for name, patch in cases.items():
            el = complete()
            for k, v in patch.items():
                setattr(el, k, v)
            self.assertFalse(el.allowed, f"{name} should block but did not")
            with self.assertRaises(PermissionError):
                require_eligible(el)

    def test_reason_text_mentions_the_cause(self):
        el = complete(); el.parallelism_deg = 0.9
        self.assertTrue(any("parallelism" in r for r in el.reasons()))
        el = complete(); el.reference_u95_mm = "UNKNOWN"
        self.assertTrue(any("U95" in r for r in el.reasons()))

    def test_json_round_trip(self):
        d = complete().to_json()
        self.assertIn("allowed", d)
        self.assertIn("blocking_reasons", d)
        self.assertTrue(d["allowed"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
