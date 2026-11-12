import type { Edge, Node } from "@xyflow/react";

import type { TopologyEdge, TopologyGroup, TopologyNode } from "./graph-types";

export interface CanvasElements {
  nodes: Node[];
  edges: Edge[];
}

const CONTAINER_PADDING = 30;
const NODE_WIDTH = 220;
const NODE_HEIGHT = 80;
const GAP_X = 20;
const GAP_Y = 20;

export function buildHierarchicalLayout(
  nodes: TopologyNode[],
  edges: TopologyEdge[],
  groups: TopologyGroup[],
): CanvasElements {
  const flowNodes: Node[] = [];
  const flowEdges: Edge[] = [];

  // Group nodes by parent container
  const childrenByParent: Record<string, TopologyNode[]> = {};
  const uncontainedNodes: TopologyNode[] = [];

  for (const n of nodes) {
    if (n.parent_id) {
      const list = childrenByParent[n.parent_id] ?? [];
      list.push(n);
      childrenByParent[n.parent_id] = list;
    } else {
      uncontainedNodes.push(n);
    }
  }

  // 1. Position groups
  let groupOffsetX = 50;
  for (const group of groups) {
    const children = childrenByParent[group.id] || [];
    const cols = Math.max(1, Math.min(3, Math.ceil(Math.sqrt(Math.max(1, children.length)))));
    const rows = Math.ceil(Math.max(1, children.length) / cols);

    const groupWidth = Math.max(300, cols * (NODE_WIDTH + GAP_X) + CONTAINER_PADDING * 2);
    const groupHeight = Math.max(180, rows * (NODE_HEIGHT + GAP_Y) + CONTAINER_PADDING * 2 + 40);

    flowNodes.push({
      id: group.id,
      type: "containerNode",
      position: { x: groupOffsetX, y: 100 },
      data: {
        label: group.name,
        groupType: group.type,
        childCount: children.length,
      },
      style: {
        width: groupWidth,
        height: groupHeight,
      },
    });

    // 2. Position children inside this container
    children.forEach((child, idx) => {
      const col = idx % cols;
      const row = Math.floor(idx / cols);

      flowNodes.push({
        id: child.id,
        type: "resourceNode",
        parentId: group.id,
        extent: "parent",
        position: {
          x: CONTAINER_PADDING + col * (NODE_WIDTH + GAP_X),
          y: CONTAINER_PADDING + 40 + row * (NODE_HEIGHT + GAP_Y),
        },
        data: {
          ...child,
        },
      });
    });

    groupOffsetX += groupWidth + 60;
  }

  // 3. Position any uncontained nodes (e.g. S3 buckets, global IAM roles)
  let uncontainedY = 100;
  for (const n of uncontainedNodes) {
    flowNodes.push({
      id: n.id,
      type: "resourceNode",
      position: { x: groupOffsetX, y: uncontainedY },
      data: {
        ...n,
      },
    });
    uncontainedY += NODE_HEIGHT + GAP_Y;
  }

  // 4. Transform edges
  for (const e of edges) {
    flowEdges.push({
      id: e.id || `edge-${e.source}-${e.target}-${e.type}`,
      source: e.source,
      target: e.target,
      type: "relationshipEdge",
      data: {
        label: e.type,
      },
    });
  }

  return { nodes: flowNodes, edges: flowEdges };
}
