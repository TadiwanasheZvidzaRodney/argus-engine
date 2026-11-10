"""Supported AWS Resource Types Catalog v1."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ResourceTypeSpec:
    cloudformation_type: str
    domain: str
    secondary_label: str
    arn_prefix: str
    supports_tags: bool = True


CATALOG_V1: dict[str, ResourceTypeSpec] = {
    # Networking
    "AWS::EC2::VPC": ResourceTypeSpec(
        cloudformation_type="AWS::EC2::VPC",
        domain="networking",
        secondary_label="Vpc",
        arn_prefix="arn:aws:ec2:{region}:{account}:vpc/",
    ),
    "AWS::EC2::Subnet": ResourceTypeSpec(
        cloudformation_type="AWS::EC2::Subnet",
        domain="networking",
        secondary_label="Subnet",
        arn_prefix="arn:aws:ec2:{region}:{account}:subnet/",
    ),
    "AWS::EC2::RouteTable": ResourceTypeSpec(
        cloudformation_type="AWS::EC2::RouteTable",
        domain="networking",
        secondary_label="RouteTable",
        arn_prefix="arn:aws:ec2:{region}:{account}:route-table/",
    ),
    "AWS::EC2::InternetGateway": ResourceTypeSpec(
        cloudformation_type="AWS::EC2::InternetGateway",
        domain="networking",
        secondary_label="InternetGateway",
        arn_prefix="arn:aws:ec2:{region}:{account}:internet-gateway/",
    ),
    "AWS::EC2::NatGateway": ResourceTypeSpec(
        cloudformation_type="AWS::EC2::NatGateway",
        domain="networking",
        secondary_label="NatGateway",
        arn_prefix="arn:aws:ec2:{region}:{account}:natgateway/",
    ),
    "AWS::EC2::SecurityGroup": ResourceTypeSpec(
        cloudformation_type="AWS::EC2::SecurityGroup",
        domain="networking",
        secondary_label="SecurityGroup",
        arn_prefix="arn:aws:ec2:{region}:{account}:security-group/",
    ),
    "AWS::EC2::NetworkInterface": ResourceTypeSpec(
        cloudformation_type="AWS::EC2::NetworkInterface",
        domain="networking",
        secondary_label="NetworkInterface",
        arn_prefix="arn:aws:ec2:{region}:{account}:network-interface/",
    ),
    # Compute
    "AWS::EC2::Instance": ResourceTypeSpec(
        cloudformation_type="AWS::EC2::Instance",
        domain="compute",
        secondary_label="Instance",
        arn_prefix="arn:aws:ec2:{region}:{account}:instance/",
    ),
    "AWS::EC2::Volume": ResourceTypeSpec(
        cloudformation_type="AWS::EC2::Volume",
        domain="compute",
        secondary_label="Volume",
        arn_prefix="arn:aws:ec2:{region}:{account}:volume/",
    ),
    # Storage
    "AWS::S3::Bucket": ResourceTypeSpec(
        cloudformation_type="AWS::S3::Bucket",
        domain="storage",
        secondary_label="Bucket",
        arn_prefix="arn:aws:s3:::",
    ),
    # Databases
    "AWS::RDS::DBInstance": ResourceTypeSpec(
        cloudformation_type="AWS::RDS::DBInstance",
        domain="database",
        secondary_label="DatabaseInstance",
        arn_prefix="arn:aws:rds:{region}:{account}:db:",
    ),
    # Identity
    "AWS::IAM::Role": ResourceTypeSpec(
        cloudformation_type="AWS::IAM::Role",
        domain="identity",
        secondary_label="Role",
        arn_prefix="arn:aws:iam::{account}:role/",
    ),
    # Load Balancing
    "AWS::ElasticLoadBalancingV2::LoadBalancer": ResourceTypeSpec(
        cloudformation_type="AWS::ElasticLoadBalancingV2::LoadBalancer",
        domain="load-balancing",
        secondary_label="LoadBalancer",
        arn_prefix="arn:aws:elasticloadbalancing:{region}:{account}:loadbalancer/",
    ),
    "AWS::ElasticLoadBalancingV2::TargetGroup": ResourceTypeSpec(
        cloudformation_type="AWS::ElasticLoadBalancingV2::TargetGroup",
        domain="load-balancing",
        secondary_label="TargetGroup",
        arn_prefix="arn:aws:elasticloadbalancing:{region}:{account}:targetgroup/",
    ),
}


def is_supported_type(cfn_type: str) -> bool:
    return cfn_type in CATALOG_V1
