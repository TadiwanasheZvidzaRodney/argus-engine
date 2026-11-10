from __future__ import annotations

import secrets

from argus_core.graph.client import build_graph_driver
from argus_core.graph.repository import GraphRepository
from argus_core.settings import Settings
from argus_worker.events.dedupe import DedupeStore
from argus_worker.events.delta_applier import DeltaApplier
from argus_worker.events.normalizer import normalize_cloudtrail_event, normalize_config_event

TENANT = "tnt_0190c3a1-0000-7000-8000-000000000001"
ACCOUNT = "123456789012"


def test_normalize_config_item_upsert() -> None:
    raw_config = {
        "configurationItem": {
            "configurationItemStatus": "OK",
            "ARN": f"arn:aws:ec2:us-east-1:{ACCOUNT}:instance/i-0abc123",
            "resourceType": "AWS::EC2::Instance",
            "awsAccountId": ACCOUNT,
            "awsRegion": "us-east-1",
            "resourceName": "web-worker-1",
            "configurationStateId": "105",
            "tags": [{"Key": "Environment", "Value": "prod"}],
            "configuration": {"instanceType": "m5.xlarge"},
        }
    }

    delta = normalize_config_event(TENANT, raw_config)
    assert delta is not None
    assert delta.change_type == "UPSERT"
    assert delta.resource_id == f"arn:aws:ec2:us-east-1:{ACCOUNT}:instance/i-0abc123"
    assert delta.version == 105
    assert delta.node is not None
    assert delta.node.tags == {"Environment": "prod"}
    assert delta.node.properties["instanceType"] == "m5.xlarge"


def test_normalize_config_item_delete() -> None:
    raw_delete = {
        "configurationItem": {
            "configurationItemStatus": "ResourceDeleted",
            "ARN": f"arn:aws:s3:::bucket-deleted-{ACCOUNT}",
            "resourceType": "AWS::S3::Bucket",
            "awsAccountId": ACCOUNT,
            "awsRegion": "us-east-1",
            "configurationStateId": "20",
        }
    }

    delta = normalize_config_event(TENANT, raw_delete)
    assert delta is not None
    assert delta.change_type == "DELETE"
    assert delta.node is None
    assert delta.version == 20


def test_normalize_cloudtrail_event() -> None:
    raw_trail = {
        "eventName": "TerminateInstances",
        "recipientAccountId": ACCOUNT,
        "awsRegion": "us-east-1",
        "userIdentity": {"arn": "arn:aws:iam::123:user/admin"},
        "resources": [{"ARN": f"arn:aws:ec2:us-east-1:{ACCOUNT}:instance/i-deadbeef"}],
    }

    delta = normalize_cloudtrail_event(TENANT, raw_trail)
    assert delta is not None
    assert delta.change_type == "DELETE"
    assert delta.actor == "arn:aws:iam::123:user/admin"
    assert delta.resource_id == f"arn:aws:ec2:us-east-1:{ACCOUNT}:instance/i-deadbeef"


async def test_dedupe_store_detects_duplicates() -> None:
    store = DedupeStore(client=None, ttl_seconds=60)
    event_id = f"evt_{secrets.token_hex(8)}"

    assert await store.is_duplicate(TENANT, event_id) is False
    # Second check must detect duplicate
    assert await store.is_duplicate(TENANT, event_id) is True


async def test_delta_applier_and_version_guard() -> None:
    driver = build_graph_driver(Settings(_env_file=None))
    repo = GraphRepository(driver)
    applier = DeltaApplier(repo, redis=None)

    unique_inst = f"i-ver-{secrets.token_hex(4)}"
    raw_event = {
        "configurationItem": {
            "configurationItemStatus": "OK",
            "ARN": f"arn:aws:ec2:us-east-1:{ACCOUNT}:instance/{unique_inst}",
            "resourceType": "AWS::EC2::Instance",
            "awsAccountId": ACCOUNT,
            "awsRegion": "us-east-1",
            "configurationStateId": "10",
        }
    }

    delta_v10 = normalize_config_event(TENANT, raw_event)
    assert delta_v10 is not None

    res1 = await applier.apply_delta(delta_v10)
    assert res1.applied is True
    assert res1.seq > 0

    # Out-of-order event with older version (v5) must be dropped
    raw_event["configurationItem"]["configurationStateId"] = "5"
    delta_v5 = normalize_config_event(TENANT, raw_event)
    assert delta_v5 is not None

    res2 = await applier.apply_delta(delta_v5)
    assert res2.applied is False
    assert res2.reason == "out-of-order version"

    await driver.close()
