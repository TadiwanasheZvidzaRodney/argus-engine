"""Synthetic URN generator for ARN-less AWS resources."""

from __future__ import annotations


def make_synthetic_urn(
    *,
    tenant_id: str,
    account_id: str,
    region: str,
    resource_type: str,
    natural_key: str,
) -> str:
    """Generate deterministic synthetic ID for resources that lack native ARNs.

    Format: urn:argus:{tenant}:{account}:{region}:{type}:{natural_key}
    """
    clean_type = resource_type.lower().replace("::", "-")
    clean_key = natural_key.strip("/").replace(" ", "-")
    return f"urn:argus:{tenant_id}:{account_id}:{region}:{clean_type}:{clean_key}"
