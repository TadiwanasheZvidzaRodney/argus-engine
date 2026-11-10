"""Synthetic enterprise topology generator for discovery testing and backfills."""

from __future__ import annotations

from argus_core.graph.models import GraphNode


def build_enterprise_topology(
    *,
    tenant_id: str,
    account_id: str,
    region: str = "us-east-1",
) -> list[GraphNode]:
    """Generates a complete VPC, subnet, compute, storage, db, alb, and IAM topology."""
    nodes: list[GraphNode] = []

    # 1. VPC
    vpc_id = f"vpc-0{account_id[:4]}1122"
    vpc_arn = f"arn:aws:ec2:{region}:{account_id}:vpc/{vpc_id}"
    nodes.append(
        GraphNode(
            id=vpc_arn,
            arn=vpc_arn,
            type="AWS::EC2::VPC",
            name=f"prod-vpc-{region}",
            tenant_id=tenant_id,
            account_id=account_id,
            region=region,
            state="available",
            tags={"Environment": "production", "ManagedBy": "Terraform"},
            properties={"cidr_block": "10.0.0.0/16", "is_default": False},
        )
    )

    # 2. Internet Gateway
    igw_id = f"igw-0{account_id[:4]}9988"
    igw_arn = f"arn:aws:ec2:{region}:{account_id}:internet-gateway/{igw_id}"
    nodes.append(
        GraphNode(
            id=igw_arn,
            arn=igw_arn,
            type="AWS::EC2::InternetGateway",
            name=f"prod-igw-{region}",
            tenant_id=tenant_id,
            account_id=account_id,
            region=region,
            state="attached",
            tags={"Environment": "production"},
            properties={"vpc_id": vpc_id},
        )
    )

    # 3. Route Table
    rt_id = f"rtb-0{account_id[:4]}3344"
    rt_arn = f"arn:aws:ec2:{region}:{account_id}:route-table/{rt_id}"
    nodes.append(
        GraphNode(
            id=rt_arn,
            arn=rt_arn,
            type="AWS::EC2::RouteTable",
            name=f"prod-public-rt-{region}",
            tenant_id=tenant_id,
            account_id=account_id,
            region=region,
            state="active",
            tags={"Environment": "production"},
            properties={"vpc_id": vpc_id, "gateway_id": igw_id},
        )
    )

    # 4. Subnet
    subnet_id = f"subnet-0{account_id[:4]}5566"
    subnet_arn = f"arn:aws:ec2:{region}:{account_id}:subnet/{subnet_id}"
    nodes.append(
        GraphNode(
            id=subnet_arn,
            arn=subnet_arn,
            type="AWS::EC2::Subnet",
            name=f"prod-app-subnet-{region}a",
            tenant_id=tenant_id,
            account_id=account_id,
            region=region,
            state="available",
            tags={"Environment": "production", "Tier": "app"},
            properties={
                "vpc_id": vpc_id,
                "route_table_id": rt_id,
                "cidr_block": "10.0.1.0/24",
                "availability_zone": f"{region}a",
            },
        )
    )

    # 5. Security Group
    sg_id = f"sg-0{account_id[:4]}7788"
    sg_arn = f"arn:aws:ec2:{region}:{account_id}:security-group/{sg_id}"
    nodes.append(
        GraphNode(
            id=sg_arn,
            arn=sg_arn,
            type="AWS::EC2::SecurityGroup",
            name=f"prod-app-sg-{region}",
            tenant_id=tenant_id,
            account_id=account_id,
            region=region,
            state="active",
            tags={"Environment": "production"},
            properties={
                "vpc_id": vpc_id,
                "group_name": "app-tier-sg",
                "inbound_ports": [80, 443],
            },
        )
    )

    # 6. IAM Role
    role_name = f"ArgusAppServiceRole-{account_id[:6]}"
    role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"
    nodes.append(
        GraphNode(
            id=role_arn,
            arn=role_arn,
            type="AWS::IAM::Role",
            name=role_name,
            tenant_id=tenant_id,
            account_id=account_id,
            region=region,
            state="active",
            tags={"Purpose": "EC2Workload"},
            properties={"assume_role_policy": "ec2.amazonaws.com"},
        )
    )

    # 7. EC2 Instance
    inst_id = f"i-0{account_id[:4]}11223344"
    inst_arn = f"arn:aws:ec2:{region}:{account_id}:instance/{inst_id}"
    nodes.append(
        GraphNode(
            id=inst_arn,
            arn=inst_arn,
            type="AWS::EC2::Instance",
            name="payments-api-worker",
            tenant_id=tenant_id,
            account_id=account_id,
            region=region,
            state="running",
            tags={"Environment": "production", "Service": "payments-api"},
            properties={
                "instance_type": "t3.large",
                "subnet_id": subnet_id,
                "vpc_id": vpc_id,
                "security_group_ids": [sg_id],
                "iam_instance_profile_arn": role_arn,
                "private_ip": "10.0.1.45",
            },
        )
    )

    # 8. EBS Volume
    vol_id = f"vol-0{account_id[:4]}aabbcc"
    vol_arn = f"arn:aws:ec2:{region}:{account_id}:volume/{vol_id}"
    nodes.append(
        GraphNode(
            id=vol_arn,
            arn=vol_arn,
            type="AWS::EC2::Volume",
            name="payments-api-data",
            tenant_id=tenant_id,
            account_id=account_id,
            region=region,
            state="in-use",
            tags={"Environment": "production"},
            properties={
                "size_gib": 100,
                "volume_type": "gp3",
                "attached_instance_id": inst_id,
            },
        )
    )

    # 9. Application Load Balancer
    alb_name = f"prod-app-alb-{region}"
    alb_arn = (
        f"arn:aws:elasticloadbalancing:{region}:{account_id}:loadbalancer/app/"
        f"{alb_name}/50dc6c495c0c9188"
    )
    tg_name = f"payments-api-tg-{region}"
    tg_arn = (
        f"arn:aws:elasticloadbalancing:{region}:{account_id}:targetgroup/{tg_name}/73e2d6bc24d8a067"
    )

    nodes.append(
        GraphNode(
            id=alb_arn,
            arn=alb_arn,
            type="AWS::ElasticLoadBalancingV2::LoadBalancer",
            name=alb_name,
            tenant_id=tenant_id,
            account_id=account_id,
            region=region,
            state="active",
            tags={"Environment": "production"},
            properties={
                "scheme": "internet-facing",
                "vpc_id": vpc_id,
                "target_group_arns": [tg_arn],
            },
        )
    )

    # 10. Target Group
    nodes.append(
        GraphNode(
            id=tg_arn,
            arn=tg_arn,
            type="AWS::ElasticLoadBalancingV2::TargetGroup",
            name=tg_name,
            tenant_id=tenant_id,
            account_id=account_id,
            region=region,
            state="active",
            tags={"Environment": "production"},
            properties={"vpc_id": vpc_id, "target_ids": [inst_id], "port": 8000},
        )
    )

    # 11. S3 Bucket
    bucket_name = f"argus-enterprise-data-{account_id}"
    bucket_arn = f"arn:aws:s3:::{bucket_name}"
    nodes.append(
        GraphNode(
            id=bucket_arn,
            arn=bucket_arn,
            type="AWS::S3::Bucket",
            name=bucket_name,
            tenant_id=tenant_id,
            account_id=account_id,
            region=region,
            state="available",
            tags={"DataClassification": "Confidential"},
            properties={"versioning": "Enabled"},
        )
    )

    # 12. RDS Database Instance
    db_id = f"payments-db-{account_id[:4]}"
    db_arn = f"arn:aws:rds:{region}:{account_id}:db:{db_id}"
    nodes.append(
        GraphNode(
            id=db_arn,
            arn=db_arn,
            type="AWS::RDS::DBInstance",
            name=db_id,
            tenant_id=tenant_id,
            account_id=account_id,
            region=region,
            state="available",
            tags={"Environment": "production"},
            properties={
                "engine": "postgres",
                "engine_version": "16.1",
                "instance_class": "db.r6g.xlarge",
                "vpc_id": vpc_id,
                "subnet_id": subnet_id,
            },
        )
    )

    return nodes
