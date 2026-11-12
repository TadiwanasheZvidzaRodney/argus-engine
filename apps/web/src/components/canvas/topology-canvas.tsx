"use client";

import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  useEdgesState,
  useNodesState,
  type Edge,
  type Node,
} from "@xyflow/react";
import React, { useEffect, useRef } from "react";

import { ContainerNode } from "./container-node";
import { RelationshipEdge } from "./relationship-edge";
import { ResourceNode } from "./resource-node";

const nodeTypes = {
  resourceNode: ResourceNode,
  containerNode: ContainerNode,
};

const edgeTypes = {
  relationshipEdge: RelationshipEdge,
};

export interface TopologyCanvasProps {
  initialNodes: Node[];
  initialEdges: Edge[];
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string | null) => void;
  fitViewTrigger: number;
}

export function TopologyCanvas({
  initialNodes,
  initialEdges,
  selectedNodeId,
  onSelectNode,
  fitViewTrigger,
}: TopologyCanvasProps) {
  const [nodes, setNodes, onNodesChange] = useNodesState(initialNodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(initialEdges);
  const flowInstanceRef = useRef<{ fitView: () => void } | null>(null);

  useEffect(() => {
    setNodes(
      initialNodes.map((n) => ({
        ...n,
        selected: n.id === selectedNodeId,
      })),
    );
    setEdges(initialEdges);
  }, [initialNodes, initialEdges, selectedNodeId, setNodes, setEdges]);

  useEffect(() => {
    if (flowInstanceRef.current && fitViewTrigger > 0) {
      flowInstanceRef.current.fitView();
    }
  }, [fitViewTrigger]);

  return (
    <div className="relative size-full overflow-hidden rounded-xl border border-border bg-background">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodesChange={onNodesChange}
        onEdgesChange={onEdgesChange}
        onNodeClick={(_event, node) => {
          if (node.type === "resourceNode") {
            onSelectNode(node.id);
          }
        }}
        onPaneClick={() => onSelectNode(null)}
        onlyRenderVisibleElements={true}
        onInit={(instance) => {
          flowInstanceRef.current = instance;
          instance.fitView({ padding: 0.2 });
        }}
        minZoom={0.1}
        maxZoom={1.5}
      >
        <Background color="var(--border)" gap={20} size={1} />
        <Controls className="!bg-surface !border-border !text-foreground !fill-foreground" />
        <MiniMap
          nodeColor={(n) => (n.type === "containerNode" ? "transparent" : "var(--accent)")}
          className="!bg-surface !border-border"
        />
      </ReactFlow>
    </div>
  );
}
