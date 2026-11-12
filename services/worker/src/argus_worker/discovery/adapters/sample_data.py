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
                "ingress_rules": [
                    {
                        "protocol": "tcp",
                        "from_port": 22,
                        "to_port": 22,
                        "cidr": "0.0.0.0/0",
                        "description": "SSH from anywhere",
                    },
                    {
                        "protocol": "tcp",
                        "from_port": 443,
                        "to_port": 443,
                        "cidr": "0.0.0.0/0",
                        "description": "HTTPS from the internet",
                    },
                    {
                        "protocol": "tcp",
                        "from_port": 8080,
                        "to_port": 8080,
                        "cidr": "10.0.0.0/8",
                        "description": "Internal service traffic",
                    },
                ],
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
            properties={
                "assume_role_policy": {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": {"Service": "ec2.amazonaws.com"},
                            "Action": "sts:AssumeRole",
                        }
                    ],
                },
                "trusted_principals": ["ec2.amazonaws.com"],
                "policy_documents": [
                    {
                        "Version": "2012-10-17",
                        "Statement": [
                            {
                                "Effect": "Allow",
                                "Action": ["s3:GetObject", "s3:ListBucket"],
                                "Resource": [
                                    f"arn:aws:s3:::argus-enterprise-data-{account_id}",
                                    f"arn:aws:s3:::argus-enterprise-data-{account_id}/*",
                                ],
                            },
                            {
                                "Effect": "Allow",
                                "Action": ["secretsmanager:GetSecretValue"],
                                "Resource": "*",
                            },
                            {
                                "Effect": "Allow",
                                "Action": ["iam:PassRole", "lambda:CreateFunction"],
                                "Resource": "*",
                            },
                        ],
                    }
                ],
            },
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
                "encrypted": False,
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
            properties={
                "versioning": "Suspended",
                "default_encryption": False,
                "tls_enforced": False,
                "policy_public": True,
                "acl_public": False,
                "public_access_block": True,
            },
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
                "storage_encrypted": False,
                "publicly_accessible": False,
            },
        )
    )

    # 13. Secrets Manager secret reachable by the application role.
    secret_arn = f"arn:aws:secretsmanager:{region}:{account_id}:secret:payments/db-creds"
    nodes.append(
        GraphNode(
            id=secret_arn,
            arn=secret_arn,
            type="AWS::SecretsManager::Secret",
            name="payments/db-creds",
            tenant_id=tenant_id,
            account_id=account_id,
            region=region,
            state="active",
            tags={"DataClassification": "Confidential"},
            properties={"rotation_enabled": False},
        )
    )

    # 14. Lambda function with an unauthenticated function URL.
    lambda_arn = f"arn:aws:lambda:{region}:{account_id}:function:payments-webhook"
    nodes.append(
        GraphNode(
            id=lambda_arn,
            arn=lambda_arn,
            type="AWS::Lambda::Function",
            name="payments-webhook",
            tenant_id=tenant_id,
            account_id=account_id,
            region=region,
            state="active",
            tags={"Environment": "production"},
            properties={
                "runtime": "python3.12",
                "role_arn": role_arn,
                "function_url_auth_type": "NONE",
            },
        )
    )

    # 15. API Gateway with an unauthenticated route.
    api_arn = f"arn:aws:apigateway:{region}::/restapis/argus-public-api"
    nodes.append(
        GraphNode(
            id=api_arn,
            arn=api_arn,
            type="AWS::ApiGateway::RestApi",
            name="payments-public-api",
            tenant_id=tenant_id,
            account_id=account_id,
            region=region,
            state="available",
            tags={"Environment": "production"},
            properties={
                "routes": [
                    {"method": "GET", "path": "/payments", "authorization": "NONE"},
                    {"method": "POST", "path": "/refunds", "authorization": "AWS_IAM"},
                ]
            },
        )
    )

    # 16. IAM user with an old access key.
    user_name = f"ci-deployer-{account_id[:6]}"
    user_arn = f"arn:aws:iam::{account_id}:user/{user_name}"
    nodes.append(
        GraphNode(
            id=user_arn,
            arn=user_arn,
            type="AWS::IAM::User",
            name=user_name,
            tenant_id=tenant_id,
            account_id=account_id,
            region=region,
            state="active",
            tags={"Purpose": "CI"},
            properties={
                "access_keys": [
                    {
                        "access_key_id": f"AKIA{account_id[:12]}",
                        "status": "Active",
                        "create_date": "2025-01-15T00:00:00+00:00",
                    }
                ]
            },
        )
    )

    # 17. Role with a wildcard trust policy.
    wildcard_role_arn = f"arn:aws:iam::{account_id}:role/PartnerIntegrationRole"
    nodes.append(
        GraphNode(
            id=wildcard_role_arn,
            arn=wildcard_role_arn,
            type="AWS::IAM::Role",
            name="PartnerIntegrationRole",
            tenant_id=tenant_id,
            account_id=account_id,
            region=region,
            state="active",
            tags={"Purpose": "Partner"},
            properties={
                "assume_role_policy": {
                    "Version": "2012-10-17",
                    "Statement": [
                        {
                            "Effect": "Allow",
                            "Principal": "*",
                            "Action": "sts:AssumeRole",
                        }
                    ],
                },
                "trusted_principals": ["*"],
            },
        )
    )

    # 18. Role trusting an account outside the organization.
    cross_account_role_arn = f"arn:aws:iam::{account_id}:role/BreakGlassAuditRole"
    nodes.append(
        GraphNode(
            id=cross_account_role_arn,
            arn=cross_account_role_arn,
            type="AWS::IAM::Role",
            name="BreakGlassAuditRole",
            tenant_id=tenant_id,
            account_id=account_id,
            region=region,
            state="active",
            tags={"Purpose": "Audit"},
            properties={
                "trusted_accounts": ["999988887777"],
                "organization_scoped": False,
            },
        )
    )

    # 19. CloudTrail trail that is not multi-region.
    trail_arn = f"arn:aws:cloudtrail:{region}:{account_id}:trail/org-trail"
    nodes.append(
        GraphNode(
            id=trail_arn,
            arn=trail_arn,
            type="AWS::CloudTrail::Trail",
            name="org-trail",
            tenant_id=tenant_id,
            account_id=account_id,
            region=region,
            state="logging",
            tags={"Environment": "production"},
            properties={"is_multi_region": False, "is_logging": True},
        )
    )

    # 20. GuardDuty detector that is disabled.
    detector_arn = f"arn:aws:guardduty:{region}:{account_id}:detector/disabled"
    nodes.append(
        GraphNode(
            id=detector_arn,
            arn=detector_arn,
            type="AWS::GuardDuty::Detector",
            name="org-detector",
            tenant_id=tenant_id,
            account_id=account_id,
            region=region,
            state="disabled",
            tags={"Environment": "production"},
            properties={"status": "DISABLED"},
        )
    )

    return nodes
