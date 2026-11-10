# Spike P0-37: Canvas Scale & Layout Engine (5,000 Nodes)

## 1. Objective
Validate the frontend canvas architecture for Phase 5. Benchmark React Flow rendering with hierarchical container grouping (Region -> VPC -> Subnet -> Security Group -> Resource) and layout computation using ELK (Eclipse Layout Kernel) inside a Web Worker at 5,000 nodes.

## 2. Key Findings

1. **Web Worker Offloading:**
   - Computing layout for 5,000 nodes and 7,500 edges in the main browser thread causes a 1.8s UI freeze.
   - Moving ELK layout to a Web Worker (`elkjs/lib/elk.bundled.js`) runs asynchronously in ~420ms without dropping frames.

2. **React Flow Optimization Tactics:**
   - **Viewport Virtualization:** `onlyRenderVisibleElements={true}` drops active DOM nodes from 5,000 to ~150 at standard zoom levels, maintaining 60 FPS during pan and zoom.
   - **Level of Detail (LOD):**
     - Zoom < 0.3: Render simplified cluster bounding boxes with badge counts.
     - Zoom 0.3–0.8: Render collapsed service nodes with status indicators.
     - Zoom > 0.8: Render full resource cards with ports, IPs, and telemetry sparklines.
   - **Edge Simplification:** Default to smoothstep edges; disable animated edge paths when edge count exceeds 500.

3. **Memory Footprint:**
   - Baseline memory consumption for 5k node state: ~48 MB.
   - Garbage collection remains smooth when state updates are batched into 100ms debounced animation frames.
