"""Sanity checks on judge-facing uncertainty calculations."""
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("judge_evidence", Path(__file__).parents[1] / "scripts/judge_evidence.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def test_perfect_small_sample_does_not_claim_certainty():
    low, high = module.wilson(13, 13)
    assert .77 < low < .78 and high == 1
    assert module.wilson(0, 8)[1] > .32
    assert module.wilson(0, 0) is None


def test_saved_evidence_counts_and_reproducibility():
    result = module.build()
    assert result == module.build()
    assert result["systems"]["tracepilot"]["count"] == 13
    assert result["reviewer"]["unsafe_approval"]["count"] == 0
    assert result["reviewer"]["correct_patch_nonapproval"]["count"] == 1
