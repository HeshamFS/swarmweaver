"use client";

import { useMemo, useState } from "react";
import type { Task } from "../hooks/useSwarmWeaver";

interface TaskGraphProps {
  tasks: Task[];
}

interface NodePosition {
  x: number;
  y: number;
  layer: number;
}

const STATUS_NODE_COLORS: Record<string, { fill: string; stroke: string }> = {
  completed: { fill: "#22c55e", stroke: "#16a34a" },
  done: { fill: "#22c55e", stroke: "#16a34a" },
  in_progress: { fill: "#6366f1", stroke: "#4f46e5" },
  pending: { fill: "#6b7280", stroke: "#4b5563" },
  blocked: { fill: "#f59e0b", stroke: "#d97706" },
  failed: { fill: "#ef4444", stroke: "#dc2626" },
  skipped: { fill: "#9ca3af", stroke: "#6b7280" },
};

function computeLayout(tasks: Task[]): Map<string, NodePosition> {
  const positions = new Map<string, NodePosition>();
  if (tasks.length === 0) return positions;

  // Build adjacency map
  const taskMap = new Map(tasks.map((t) => [t.id, t]));
  const inDegree = new Map<string, number>();
  const children = new Map<string, string[]>();

  for (const task of tasks) {
    inDegree.set(task.id, 0);
    children.set(task.id, []);
  }
  for (const task of tasks) {
    if (task.depends_on) {
      for (const dep of task.depends_on) {
        if (taskMap.has(dep)) {
          inDegree.set(task.id, (inDegree.get(task.id) || 0) + 1);
          children.get(dep)?.push(task.id);
        }
      }
    }
  }

  // Topological sort (Kahn's algorithm) to assign layers
  const queue: string[] = [];
  const layers = new Map<string, number>();

  for (const [id, deg] of inDegree) {
    if (deg === 0) {
      queue.push(id);
      layers.set(id, 0);
    }
  }

  let maxLayer = 0;
  while (queue.length > 0) {
    const current = queue.shift()!;
    const currentLayer = layers.get(current) || 0;
    for (const child of children.get(current) || []) {
      const newLayer = currentLayer + 1;
      layers.set(child, Math.max(layers.get(child) || 0, newLayer));
      maxLayer = Math.max(maxLayer, newLayer);
      const newDeg = (inDegree.get(child) || 1) - 1;
      inDegree.set(child, newDeg);
      if (newDeg === 0) {
        queue.push(child);
      }
    }
  }

  // Handle any remaining tasks (cycles) - assign to last layer
  for (const task of tasks) {
    if (!layers.has(task.id)) {
      layers.set(task.id, maxLayer + 1);
    }
  }

  // Group tasks by layer
  const layerGroups = new Map<number, string[]>();
  for (const [id, layer] of layers) {
    if (!layerGroups.has(layer)) layerGroups.set(layer, []);
    layerGroups.get(layer)!.push(id);
  }

  // Position nodes
  const nodeWidth = 160;
  const nodeHeight = 50;
  const horizontalGap = 60;
  const verticalGap = 30;

  for (const [layer, ids] of layerGroups) {
    for (let i = 0; i < ids.length; i++) {
      positions.set(ids[i], {
        x: layer * (nodeWidth + horizontalGap) + 40,
        y: i * (nodeHeight + verticalGap) + 40,
        layer,
      });
    }
  }

  return positions;
}

export function TaskGraph({ tasks }: TaskGraphProps) {
  const [hoveredTask, setHoveredTask] = useState<string | null>(null);

  const positions = useMemo(() => computeLayout(tasks), [tasks]);

  if (tasks.length === 0) {
    return (
      <div className="flex items-center justify-center h-full">
        <span className="text-sm text-text-muted">No tasks to visualize.</span>
      </div>
    );
  }

  // Calculate SVG dimensions
  let maxX = 0;
  let maxY = 0;
  for (const pos of positions.values()) {
    maxX = Math.max(maxX, pos.x + 160);
    maxY = Math.max(maxY, pos.y + 50);
  }
  const svgWidth = maxX + 40;
  const svgHeight = maxY + 40;

  // Build edges
  const edges: { from: string; to: string }[] = [];
  for (const task of tasks) {
    if (task.depends_on) {
      for (const dep of task.depends_on) {
        if (positions.has(dep) && positions.has(task.id)) {
          edges.push({ from: dep, to: task.id });
        }
      }
    }
  }

  const taskMap = new Map(tasks.map((t) => [t.id, t]));

  return (
    <div className="w-full h-full overflow-auto">
      <svg
        width={Math.max(svgWidth, 300)}
        height={Math.max(svgHeight, 200)}
        className="font-mono"
      >
        <defs>
          <marker
            id="arrowhead"
            markerWidth="8"
            markerHeight="6"
            refX="8"
            refY="3"
            orient="auto"
          >
            <polygon points="0 0, 8 3, 0 6" fill="#6b7280" />
          </marker>
        </defs>

        {/* Edges */}
        {edges.map(({ from, to }, i) => {
          const fromPos = positions.get(from)!;
          const toPos = positions.get(to)!;
          const x1 = fromPos.x + 160;
          const y1 = fromPos.y + 25;
          const x2 = toPos.x;
          const y2 = toPos.y + 25;
          const isHighlighted =
            hoveredTask === from || hoveredTask === to;
          return (
            <line
              key={i}
              x1={x1}
              y1={y1}
              x2={x2}
              y2={y2}
              stroke={isHighlighted ? "#6366f1" : "#4b5563"}
              strokeWidth={isHighlighted ? 2 : 1}
              markerEnd="url(#arrowhead)"
              opacity={isHighlighted ? 1 : 0.5}
            />
          );
        })}

        {/* Nodes */}
        {tasks.map((task) => {
          const pos = positions.get(task.id);
          if (!pos) return null;
          const colors =
            STATUS_NODE_COLORS[task.status] || STATUS_NODE_COLORS.pending;
          const isHovered = hoveredTask === task.id;

          return (
            <g
              key={task.id}
              onMouseEnter={() => setHoveredTask(task.id)}
              onMouseLeave={() => setHoveredTask(null)}
              className="cursor-pointer"
            >
              <rect
                x={pos.x}
                y={pos.y}
                width={150}
                height={44}
                rx={6}
                fill={isHovered ? colors.stroke : colors.fill}
                stroke={colors.stroke}
                strokeWidth={isHovered ? 2 : 1}
                opacity={0.9}
              />
              <text
                x={pos.x + 75}
                y={pos.y + 18}
                textAnchor="middle"
                fill="white"
                fontSize={10}
                fontWeight="bold"
              >
                {task.title.length > 20
                  ? task.title.slice(0, 18) + "..."
                  : task.title}
              </text>
              <text
                x={pos.x + 75}
                y={pos.y + 32}
                textAnchor="middle"
                fill="rgba(255,255,255,0.7)"
                fontSize={9}
              >
                {task.status} {task.id ? `(${task.id})` : ""}
              </text>
            </g>
          );
        })}

        {/* Tooltip */}
        {hoveredTask && (() => {
          const task = taskMap.get(hoveredTask);
          const pos = positions.get(hoveredTask);
          if (!task || !pos) return null;
          const tooltipX = pos.x;
          const tooltipY = pos.y + 54;
          return (
            <g>
              <rect
                x={tooltipX}
                y={tooltipY}
                width={200}
                height={50}
                rx={4}
                fill="#1f2937"
                stroke="#374151"
                strokeWidth={1}
              />
              <text
                x={tooltipX + 8}
                y={tooltipY + 16}
                fill="#e5e7eb"
                fontSize={10}
              >
                {task.title.slice(0, 30)}
              </text>
              <text
                x={tooltipX + 8}
                y={tooltipY + 30}
                fill="#9ca3af"
                fontSize={9}
              >
                {task.category || "general"} | P{task.priority || 0}
              </text>
              <text
                x={tooltipX + 8}
                y={tooltipY + 42}
                fill="#9ca3af"
                fontSize={9}
              >
                {task.depends_on?.length
                  ? `Deps: ${task.depends_on.join(", ")}`
                  : "No dependencies"}
              </text>
            </g>
          );
        })()}
      </svg>
    </div>
  );
}
