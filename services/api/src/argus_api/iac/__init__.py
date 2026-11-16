"""Phase 10: GitOps Bridge, IaC Drift Detection, and PR Synthesis."""

from __future__ import annotations

from argus_api.iac.drift import detect_iac_drift
from argus_api.iac.synthesizer import synthesize_hcl_diff
from argus_api.iac.vcs import create_or_simulate_pull_request

__all__ = [
    "create_or_simulate_pull_request",
    "detect_iac_drift",
    "synthesize_hcl_diff",
]
