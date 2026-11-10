"""Infers typed directed relationships between discovered graph nodes."""

from __future__ import annotations

from argus_core.graph.models import GraphEdge, GraphNode


class RelationshipResolver:
    """Infers typed edges from node configurations."""

    @staticmethod
    def resolve(tenant_id: str, nodes: list[GraphNode]) -> list[GraphEdge]:
        edges: list[GraphEdge] = []

        # Index nodes by ARN and by natural resource ID (e.g. vpc-..., subnet-..., i-...)
        by_arn: dict[str, GraphNode] = {n.arn: n for n in nodes}
        by_natural_id: dict[str, GraphNode] = {}
        for n in nodes:
            # Extract natural id from ARN suffix
            natural = n.arn.split("/")[-1].split(":")[-1]
            if natural:
                by_natural_id[natural] = n

        for node in nodes:
            props = node.properties

            # 1. Subnet -> VPC (VPC CONTAINS Subnet)
            if node.type == "AWS::EC2::Subnet":
                vpc_id = props.get("vpc_id")
                if vpc_id and vpc_id in by_natural_id:
                    edges.append(
                        GraphEdge(
                            source_id=by_natural_id[vpc_id].id,
                            target_id=node.id,
                            type="CONTAINS",
                            tenant_id=tenant_id,
                        )
                    )

                # Subnet -> RouteTable (Subnet ROUTES_TO RouteTable)
                rt_id = props.get("route_table_id")
                if rt_id and rt_id in by_natural_id:
                    edges.append(
                        GraphEdge(
                            source_id=node.id,
                            target_id=by_natural_id[rt_id].id,
                            type="ROUTES_TO",
                            tenant_id=tenant_id,
                        )
                    )

            # 2. RouteTable -> InternetGateway
            if node.type == "AWS::EC2::RouteTable":
                gw_id = props.get("gateway_id")
                if gw_id and gw_id in by_natural_id:
                    edges.append(
                        GraphEdge(
                            source_id=node.id,
                            target_id=by_natural_id[gw_id].id,
                            type="ROUTES_TO",
                            tenant_id=tenant_id,
                        )
                    )

            # 3. Instance relationships
            if node.type == "AWS::EC2::Instance":
                subnet_id = props.get("subnet_id")
                if subnet_id and subnet_id in by_natural_id:
                    edges.append(
                        GraphEdge(
                            source_id=by_natural_id[subnet_id].id,
                            target_id=node.id,
                            type="CONTAINS",
                            tenant_id=tenant_id,
                        )
                    )

                for sg_id in props.get("security_group_ids", []):
                    if sg_id in by_natural_id:
                        edges.append(
                            GraphEdge(
                                source_id=node.id,
                                target_id=by_natural_id[sg_id].id,
                                type="MEMBER_OF",
                                tenant_id=tenant_id,
                            )
                        )

                role_arn = props.get("iam_instance_profile_arn")
                if role_arn and role_arn in by_arn:
                    edges.append(
                        GraphEdge(
                            source_id=node.id,
                            target_id=by_arn[role_arn].id,
                            type="ASSUMES",
                            tenant_id=tenant_id,
                        )
                    )

            # 4. Volume -> Instance (ATTACHED_TO)
            if node.type == "AWS::EC2::Volume":
                inst_id = props.get("attached_instance_id")
                if inst_id and inst_id in by_natural_id:
                    edges.append(
                        GraphEdge(
                            source_id=node.id,
                            target_id=by_natural_id[inst_id].id,
                            type="ATTACHED_TO",
                            tenant_id=tenant_id,
                        )
                    )

            # 5. LoadBalancer -> TargetGroup
            if node.type == "AWS::ElasticLoadBalancingV2::LoadBalancer":
                for tg_arn in props.get("target_group_arns", []):
                    if tg_arn in by_arn:
                        edges.append(
                            GraphEdge(
                                source_id=node.id,
                                target_id=by_arn[tg_arn].id,
                                type="ROUTES_TO",
                                tenant_id=tenant_id,
                            )
                        )

            # 6. TargetGroup -> Target (Instance)
            if node.type == "AWS::ElasticLoadBalancingV2::TargetGroup":
                for target_id in props.get("target_ids", []):
                    if target_id in by_natural_id:
                        edges.append(
                            GraphEdge(
                                source_id=node.id,
                                target_id=by_natural_id[target_id].id,
                                type="TARGETS",
                                tenant_id=tenant_id,
                            )
                        )

            # 7. RDS Instance -> Subnet
            if node.type == "AWS::RDS::DBInstance":
                subnet_id = props.get("subnet_id")
                if subnet_id and subnet_id in by_natural_id:
                    edges.append(
                        GraphEdge(
                            source_id=by_natural_id[subnet_id].id,
                            target_id=node.id,
                            type="CONTAINS",
                            tenant_id=tenant_id,
                        )
                    )

        return edges
