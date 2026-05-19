"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Paper from "@mui/material/Paper";
import Chip from "@mui/material/Chip";
import Button from "@mui/material/Button";
import LinearProgress from "@mui/material/LinearProgress";
import Grid from "@mui/material/Grid";
import Divider from "@mui/material/Divider";
import RefreshIcon from "@mui/icons-material/Refresh";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlined";
import ScienceOutlinedIcon from "@mui/icons-material/ScienceOutlined";
import HubOutlinedIcon from "@mui/icons-material/HubOutlined";
import WarningAmberOutlinedIcon from "@mui/icons-material/WarningAmberOutlined";
import PersonOutlineOutlinedIcon from "@mui/icons-material/PersonOutlineOutlined";
import AccountTreeOutlinedIcon from "@mui/icons-material/AccountTreeOutlined";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";

import {
  ReactFlow,
  Background,
  Controls,
  Handle,
  Position,
  type Node,
  type Edge,
  type NodeTypes,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
type Contributor = {
  developer_username: string;
  developer_identity: string;
  commit_count: number;
  expertise_score: number;
  external: boolean;
  demo?: boolean;
};

type Module = {
  path: string;
  owners: string[];
  bus_factor: number;
  contributors: Contributor[];
  demo?: boolean;
};

type Developer = {
  username: string;
  name: string;
  active: boolean;
  external: boolean;
  demo?: boolean;
};

type Finding = {
  subject: string;
  concern_type: string;
  narrative: string;
};

type GraphData = {
  developers: Developer[];
  upstream_authors: Developer[];
  modules: Module[];
  concentrated_modules?: Module[];
  recent_findings?: Finding[];
};

// ---------------------------------------------------------------------------
// Concentration helpers — bus_factor is a measurement, not a score.
// Colour conveys structural concentration, never severity.
// ---------------------------------------------------------------------------
function concentrationLabel(busFactor: number, hasInternal: boolean): string {
  if (!hasInternal) return "no internal";
  if (busFactor <= 1) return "sole holder";
  if (busFactor === 2) return "pair-held";
  return "distributed";
}

function concentrationColor(busFactor: number, hasInternal: boolean): string {
  if (!hasInternal) return "#ea4335";   // no internal knowledge — red, descriptive
  if (busFactor <= 1) return "#fa7b17"; // single holder — orange
  if (busFactor === 2) return "#fbbc04";
  return "#34a853";
}

function moduleSortKey(m: Module): number {
  // Sort modules so the structurally most-concentrated come first.
  // bus_factor=0 (no internal committers) first, then 1, 2, ...
  const internal = (m.contributors ?? []).filter((c) => !c.external && c.commit_count > 0).length;
  if (internal === 0) return -1;
  return m.bus_factor || 0;
}

// ---------------------------------------------------------------------------
// React Flow — custom node types (defined outside component to avoid re-render)
// ---------------------------------------------------------------------------
const DEMO_DOT = (
  <Box component="span" sx={{
    display: "inline-block", width: 6, height: 6, borderRadius: "50%",
    bgcolor: "#a78bfa", ml: 0.5, verticalAlign: "middle", flexShrink: 0,
  }} />
);

function ModuleFlowNode({ data }: { data: Record<string, unknown> }) {
  const busFactor = (data.busFactor as number) ?? 0;
  const hasInternal = (data.hasInternal as boolean) ?? false;
  const path = data.path as string;
  const isDemo = (data.demo as boolean) ?? false;
  const color = concentrationColor(busFactor, hasInternal);
  const label = concentrationLabel(busFactor, hasInternal);
  return (
    <Box
      sx={{
        px: 1.5,
        py: 0.75,
        bgcolor: color + "18",
        border: `1px solid ${isDemo ? "#7c3aed88" : color + "55"}`,
        borderRadius: 1.5,
        minWidth: 130,
        cursor: "default",
        userSelect: "none",
        outline: isDemo ? "1px dashed #7c3aed44" : "none",
        outlineOffset: 2,
      }}
    >
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
        <Typography
          sx={{ color, fontFamily: "monospace", fontWeight: 700, fontSize: "0.7rem", lineHeight: 1.4, flex: 1 }}
        >
          {path}/
        </Typography>
        {isDemo && DEMO_DOT}
      </Box>
      <Typography sx={{ color, opacity: 0.7, fontSize: "0.58rem", lineHeight: 1 }}>
        {label} · bus {busFactor}
      </Typography>
      <Handle type="source" position={Position.Right} style={{ background: color, border: "none", width: 7, height: 7 }} />
    </Box>
  );
}

function ContributorFlowNode({ data }: { data: Record<string, unknown> }) {
  const external = data.external as boolean;
  const username = data.username as string;
  const isDemo = (data.demo as boolean) ?? false;
  const color = isDemo ? "#a78bfa" : external ? "#fa7b17" : "#4285f4";
  return (
    <Box
      sx={{
        px: 1.25,
        py: 0.4,
        bgcolor: color + "15",
        border: `1px solid ${color}44`,
        borderRadius: 4,
        minWidth: 100,
        cursor: "default",
        userSelect: "none",
      }}
    >
      <Handle type="target" position={Position.Left} style={{ background: color, border: "none", width: 7, height: 7 }} />
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.5 }}>
        <Typography sx={{ color, fontFamily: "monospace", fontSize: "0.68rem", lineHeight: 1.5 }}>
          {username}
        </Typography>
        {isDemo && DEMO_DOT}
      </Box>
    </Box>
  );
}

const nodeTypes: NodeTypes = {
  moduleNode: ModuleFlowNode,
  contributorNode: ContributorFlowNode,
};

// ---------------------------------------------------------------------------
// Build React Flow graph data from modules
// ---------------------------------------------------------------------------
const MOD_X = 16;
const CTB_COL1_X = 430;
const CTB_COL2_X = 610;
const MOD_GAP = 68;
const CTB_GAP = 44;

function buildFlowGraph(modules: Module[]): { nodes: Node[]; edges: Edge[]; totalHeight: number } {
  // Show the 25 structurally most-concentrated modules with contributor data.
  // Concentration is a measurement (bus_factor), not a score.
  const visModules = [...modules]
    .filter((m) => (m.contributors?.length ?? 0) > 0)
    .sort((a, b) => moduleSortKey(a) - moduleSortKey(b))
    .slice(0, 25);

  // Collect ALL unique contributors across those modules.
  // When a contributor appears in multiple modules, keep the highest expertise_score.
  const contribMap = new Map<string, Contributor>();
  for (const mod of visModules) {
    for (const c of mod.contributors ?? []) {
      const prev = contribMap.get(c.developer_username);
      if (!prev || c.expertise_score > prev.expertise_score) {
        contribMap.set(c.developer_username, c);
      }
    }
  }
  // Sort: internal first (so they're at the top of column 1), then by expertise desc
  const allContribs = [...contribMap.values()].sort((a, b) => {
    if (a.external !== b.external) return a.external ? 1 : -1;
    return b.expertise_score - a.expertise_score;
  });

  // Split into 2 columns to halve the height
  const col1 = allContribs.filter((_, i) => i % 2 === 0);
  const col2 = allContribs.filter((_, i) => i % 2 === 1);

  const modTotalH = Math.max(0, visModules.length - 1) * MOD_GAP;
  const col1TotalH = Math.max(0, col1.length - 1) * CTB_GAP;
  const col2TotalH = Math.max(0, col2.length - 1) * CTB_GAP;
  const totalHeight = Math.max(modTotalH, col1TotalH, col2TotalH) + 100;

  const modStartY = (totalHeight - modTotalH) / 2;
  const col1StartY = (totalHeight - col1TotalH) / 2;
  const col2StartY = (totalHeight - col2TotalH) / 2 + CTB_GAP / 2; // offset so they interleave visually

  const nodes: Node[] = [
    ...visModules.map((mod, i) => {
      const hasInternal = (mod.contributors ?? []).some((c) => !c.external && c.commit_count > 0);
      const isDemo = mod.demo || (mod.contributors ?? []).some((c) => c.demo);
      return {
        id: `mod-${mod.path}`,
        type: "moduleNode" as const,
        position: { x: MOD_X, y: modStartY + i * MOD_GAP },
        data: { path: mod.path, busFactor: mod.bus_factor ?? 0, hasInternal, demo: isDemo },
        draggable: false,
      };
    }),
    ...col1.map((c, i) => ({
      id: `ctb-${c.developer_username}`,
      type: "contributorNode" as const,
      position: { x: CTB_COL1_X, y: col1StartY + i * CTB_GAP },
      data: { username: c.developer_username, external: c.external, demo: c.demo ?? false },
      draggable: false,
    })),
    ...col2.map((c, i) => ({
      id: `ctb-${c.developer_username}`,
      type: "contributorNode" as const,
      position: { x: CTB_COL2_X, y: col2StartY + i * CTB_GAP },
      data: { username: c.developer_username, external: c.external, demo: c.demo ?? false },
      draggable: false,
    })),
  ];

  const contribSet = new Set(allContribs.map((c) => c.developer_username));
  const edges: Edge[] = [];
  for (const mod of visModules) {
    for (const c of mod.contributors ?? []) {
      if (!contribSet.has(c.developer_username)) continue;
      const color = c.external ? "#fa7b17" : "#4285f4";
      edges.push({
        id: `${mod.path}__${c.developer_username}`,
        source: `mod-${mod.path}`,
        target: `ctb-${c.developer_username}`,
        style: {
          stroke: color,
          strokeWidth: Math.max(0.5, c.expertise_score * 3),
          strokeOpacity: Math.max(0.1, c.expertise_score * 0.7),
        },
        type: "default",
      });
    }
  }

  return { nodes, edges, totalHeight };
}

// ---------------------------------------------------------------------------
// Module Knowledge Breakdown — the primary view
// ---------------------------------------------------------------------------
function ModuleBreakdown({ modules, findings }: { modules: Module[]; findings: Finding[] }) {
  // Detect if data is still in the seeding-only state (only "repository" exists)
  const hasOnlyRoot = modules.length <= 1 && modules[0]?.path === "repository";

  // Sort by structural concentration (a measurement). Modules with no internal
  // committers float to the top; then by bus_factor ascending.
  const sorted = [...modules]
    .filter((m) => (m.contributors?.length ?? 0) > 0)
    .sort((a, b) => moduleSortKey(a) - moduleSortKey(b));

  // Build per-module finding index so each card can surface concern types.
  const findingsByModule = new Map<string, Finding[]>();
  for (const f of findings) {
    const key = f.subject;
    if (!findingsByModule.has(key)) findingsByModule.set(key, []);
    findingsByModule.get(key)!.push(f);
  }

  if (sorted.length === 0) {
    return (
      <Typography variant="body2" color="text.disabled">
        No module data yet — run the pipeline to populate per-directory knowledge.
      </Typography>
    );
  }

  return (
    <Stack spacing={1.25}>
      {hasOnlyRoot && (
        <Paper
          elevation={0}
          sx={{ p: 1.5, bgcolor: "rgba(66,133,244,0.06)", border: "1px solid rgba(66,133,244,0.2)", borderRadius: 2 }}
        >
          <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
            <InfoOutlinedIcon sx={{ fontSize: 15, color: "primary.light", flexShrink: 0 }} />
            <Typography variant="caption" color="text.secondary">
              Only global data so far. Per-directory breakdown (who knows{" "}
              <Box component="span" sx={{ fontFamily: "var(--font-google-sans-code)", color: "primary.light" }}>internal/</Box>,{" "}
              <Box component="span" sx={{ fontFamily: "var(--font-google-sans-code)", color: "primary.light" }}>app/</Box>, etc.)
              appears once Map Modules collects per-directory commits. Check pipeline logs for{" "}
              <Box component="span" sx={{ fontFamily: "var(--font-google-sans-code)", color: "primary.light" }}>get_top_level_dirs</Box>.
            </Typography>
          </Stack>
        </Paper>
      )}

      {sorted.map((mod) => {
        const contribs = [...(mod.contributors ?? [])].sort((a, b) => b.expertise_score - a.expertise_score);
        const internalCommitters = contribs.filter((c) => !c.external && c.commit_count > 0);
        const hasInternal = internalCommitters.length > 0;
        const noInternalKnowledge = !hasInternal && contribs.length > 0;
        const showTop = contribs.slice(0, 10);
        const hiddenCount = contribs.length - showTop.length;
        const busFactor = mod.bus_factor ?? 0;
        const color = concentrationColor(busFactor, hasInternal);
        const label = concentrationLabel(busFactor, hasInternal);
        const moduleFindings = findingsByModule.get(mod.path) ?? [];
        const isDemo = mod.demo || contribs.some((c) => c.demo);

        return (
          <Paper
            key={mod.path}
            elevation={0}
            sx={{
              p: 2,
              bgcolor: "rgba(255,255,255,0.02)",
              border: "1px solid",
              borderColor: noInternalKnowledge
                ? "rgba(234,67,53,0.25)"
                : busFactor <= 1
                ? "rgba(250,123,23,0.15)"
                : "rgba(255,255,255,0.06)",
              borderRadius: 2,
            }}
          >
            {/* Module header */}
            <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1.25, flexWrap: "wrap" }} useFlexGap>
              <Chip
                label={label}
                size="small"
                sx={{ bgcolor: color + "1a", color, border: `1px solid ${color}55`, height: 20, fontSize: "0.65rem", fontWeight: 700, flexShrink: 0 }}
              />
              <Typography
                variant="body2"
                sx={{ fontFamily: "var(--font-google-sans-code)", fontWeight: 600, flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
              >
                {mod.path}/
              </Typography>
              <Typography variant="caption" color="text.disabled" sx={{ flexShrink: 0 }}>
                bus factor {busFactor}
              </Typography>
              {noInternalKnowledge && (
                <>
                  <Divider orientation="vertical" flexItem sx={{ borderColor: "rgba(255,255,255,0.08)" }} />
                  <Chip
                    label="no internal experts"
                    size="small"
                    color="error"
                    variant="outlined"
                    icon={<WarningAmberOutlinedIcon sx={{ fontSize: "11px !important" }} />}
                    sx={{ height: 18, fontSize: "0.6rem", flexShrink: 0 }}
                  />
                </>
              )}
              {moduleFindings.map((f, i) => (
                <Chip
                  key={i}
                  label={f.concern_type.replace(/_/g, " ")}
                  size="small"
                  variant="outlined"
                  sx={{ height: 18, fontSize: "0.6rem", flexShrink: 0, color: "primary.light", borderColor: "rgba(138,180,248,0.4)" }}
                />
              ))}
              {isDemo && (
                <Chip
                  label="demo"
                  size="small"
                  icon={<ScienceOutlinedIcon sx={{ fontSize: "11px !important" }} />}
                  sx={{ height: 18, fontSize: "0.6rem", flexShrink: 0, color: "#a78bfa", borderColor: "#7c3aed55", bgcolor: "#7c3aed11", border: "1px solid" }}
                />
              )}
            </Stack>

            {/* Contributor rows */}
            <Stack spacing={0.6}>
              {showTop.map((c, i) => {
                const contribColor = c.external ? "#fa7b17" : "#4285f4";
                return (
                  <Stack key={c.developer_username} direction="row" spacing={1} sx={{ alignItems: "center" }}>
                    <Typography
                      variant="caption"
                      sx={{ color: i === 0 ? contribColor : "rgba(255,255,255,0.2)", fontWeight: i === 0 ? 700 : 400, minWidth: 14, flexShrink: 0, fontFamily: "var(--font-google-sans-code)" }}
                    >
                      {i === 0 ? "▶" : "·"}
                    </Typography>
                    <Typography
                      variant="caption"
                      sx={{ fontFamily: "var(--font-google-sans-code)", color: contribColor, minWidth: 130, maxWidth: 130, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", flexShrink: 0 }}
                    >
                      {c.developer_username}
                    </Typography>
                    <Box sx={{ flex: 1, minWidth: 60 }}>
                      <LinearProgress
                        variant="determinate"
                        value={Math.round(c.expertise_score * 100)}
                        sx={{
                          height: 4, borderRadius: 2, bgcolor: "rgba(255,255,255,0.05)",
                          "& .MuiLinearProgress-bar": { bgcolor: contribColor, borderRadius: 2, opacity: 0.85 },
                        }}
                      />
                    </Box>
                    <Typography
                      variant="caption"
                      sx={{ fontFamily: "var(--font-google-sans-code)", color: contribColor, minWidth: 32, textAlign: "right", flexShrink: 0 }}
                    >
                      {c.expertise_score.toFixed(2)}
                    </Typography>
                    <Chip
                      label={c.external ? "upstream" : "internal"}
                      size="small"
                      variant="outlined"
                      sx={{ height: 16, fontSize: "0.58rem", minWidth: 58, flexShrink: 0, color: contribColor, borderColor: contribColor + "44" }}
                    />
                    {c.demo && (
                      <Chip
                        label="demo"
                        size="small"
                        sx={{ height: 16, fontSize: "0.58rem", flexShrink: 0, color: "#a78bfa", bgcolor: "#7c3aed11", border: "1px solid #7c3aed55" }}
                      />
                    )}
                    {c.commit_count > 0 && (
                      <Typography variant="caption" color="text.disabled" sx={{ minWidth: 60, textAlign: "right", flexShrink: 0 }}>
                        {c.commit_count} commits
                      </Typography>
                    )}
                  </Stack>
                );
              })}
              {hiddenCount > 0 && (
                <Typography variant="caption" color="text.disabled" sx={{ pl: "22px" }}>
                  +{hiddenCount} more contributor{hiddenCount !== 1 ? "s" : ""}
                </Typography>
              )}
            </Stack>
          </Paper>
        );
      })}
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Upstream authors — contributor-centric "who knows what" view
// ---------------------------------------------------------------------------
function UpstreamAuthorList({ authors, modules }: { authors: Developer[]; modules: Module[] }) {
  // Build username → contributed modules (external contribs only, skip pure "repository" global)
  const authorModules = useMemo(() => {
    const map: Record<string, Array<{ path: string; commit_count: number; expertise_score: number }>> = {};
    for (const mod of modules) {
      if (mod.path === "repository") continue; // skip the global catch-all
      for (const c of mod.contributors ?? []) {
        if (!c.external) continue;
        if (!map[c.developer_username]) map[c.developer_username] = [];
        map[c.developer_username].push({
          path: mod.path,
          commit_count: c.commit_count,
          expertise_score: c.expertise_score,
        });
      }
    }
    // sort each author's modules by expertise desc
    for (const k of Object.keys(map)) {
      map[k].sort((a, b) => b.expertise_score - a.expertise_score);
    }
    return map;
  }, [modules]);

  const hasPerDirData = Object.keys(authorModules).length > 0;

  return (
    <Stack spacing={1.25} sx={{ maxHeight: 420, overflowY: "auto", overflowX: "hidden" }}>
      {!hasPerDirData && (
        <Paper elevation={0} sx={{ p: 1.5, bgcolor: "rgba(66,133,244,0.06)", border: "1px solid rgba(66,133,244,0.15)", borderRadius: 1.5 }}>
          <Stack direction="row" spacing={1} sx={{ alignItems: "flex-start" }}>
            <InfoOutlinedIcon sx={{ fontSize: 13, color: "primary.light", flexShrink: 0, mt: 0.25 }} />
            <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.5 }}>
              Per-directory attribution not yet available. Run the pipeline to map which parts of the repo each author contributed to.
            </Typography>
          </Stack>
        </Paper>
      )}
      {authors.map((dev) => {
        const mods = authorModules[dev.username] ?? [];
        const totalCommits = mods.reduce((s, m) => s + m.commit_count, 0);
        return (
          <Box key={dev.username} sx={{ pb: 1, borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
            <Stack direction="row" spacing={0.75} sx={{ alignItems: "center", mb: mods.length ? 0.6 : 0 }}>
              <PersonOutlineOutlinedIcon sx={{ fontSize: 13, color: dev.demo ? "#a78bfa" : "#fa7b17", flexShrink: 0 }} />
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="caption" sx={{ fontFamily: "var(--font-google-sans-code)", color: dev.demo ? "#a78bfa" : "#fa7b17", display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {dev.name || dev.username}
                </Typography>
              </Box>
              {dev.demo && (
                <Chip label="demo" size="small" icon={<ScienceOutlinedIcon sx={{ fontSize: "10px !important" }} />}
                  sx={{ height: 15, fontSize: "0.55rem", color: "#a78bfa", bgcolor: "#7c3aed11",
                        border: "1px solid #7c3aed55", "& .MuiChip-label": { px: 0.5 }, flexShrink: 0 }} />
              )}
              {totalCommits > 0 && (
                <Typography variant="caption" color="text.disabled" sx={{ flexShrink: 0, fontFamily: "var(--font-google-sans-code)" }}>
                  {totalCommits} commits
                </Typography>
              )}
            </Stack>
            {mods.length > 0 ? (
              <Stack spacing={0.3} sx={{ pl: 2.5 }}>
                {mods.slice(0, 4).map((m) => (
                  <Stack key={m.path} direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
                    <Typography variant="caption" sx={{ fontFamily: "var(--font-google-sans-code)", color: "rgba(255,255,255,0.35)", fontSize: "0.6rem", minWidth: 70, maxWidth: 70, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {m.path}/
                    </Typography>
                    <Box sx={{ flex: 1 }}>
                      <LinearProgress
                        variant="determinate"
                        value={Math.round(m.expertise_score * 100)}
                        sx={{
                          height: 3, borderRadius: 1, bgcolor: "rgba(250,123,23,0.1)",
                          "& .MuiLinearProgress-bar": { bgcolor: "#fa7b17", borderRadius: 1, opacity: 0.7 },
                        }}
                      />
                    </Box>
                    <Typography variant="caption" sx={{ fontFamily: "var(--font-google-sans-code)", color: "rgba(250,123,23,0.6)", fontSize: "0.6rem", minWidth: 40, textAlign: "right", flexShrink: 0 }}>
                      {m.commit_count} commits
                    </Typography>
                  </Stack>
                ))}
                {mods.length > 4 && (
                  <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.6rem" }}>
                    +{mods.length - 4} more areas
                  </Typography>
                )}
              </Stack>
            ) : (
              <Typography variant="caption" color="text.disabled" sx={{ pl: 2.5, fontSize: "0.6rem" }}>
                global commits only (no per-dir data yet)
              </Typography>
            )}
          </Box>
        );
      })}
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// React Flow structural overview
// ---------------------------------------------------------------------------
function StructuralOverview({ modules }: { modules: Module[] }) {
  const { nodes, edges, totalHeight } = useMemo(() => buildFlowGraph(modules), [modules]);

  if (nodes.length === 0) return null;

  const contribCount = nodes.filter((n) => n.type === "contributorNode").length;
  const modCount = nodes.filter((n) => n.type === "moduleNode").length;

  return (
    <Stack spacing={1}>
      <Typography variant="caption" color="text.disabled">
        {modCount} modules · {contribCount} contributors · drag to pan · scroll controls to zoom
      </Typography>
      <Box
        sx={{
          // Cap visible height at 600px; user pans to see the full graph
          height: Math.min(totalHeight, 600),
          minHeight: 300,
          width: "100%",
          borderRadius: 2,
          overflow: "hidden",
          border: "1px solid rgba(255,255,255,0.06)",
          "& .react-flow__background": { bgcolor: "transparent" },
          "& .react-flow__controls button": {
            bgcolor: "rgba(255,255,255,0.06)",
            border: "1px solid rgba(255,255,255,0.1)",
            color: "rgba(255,255,255,0.6)",
            "&:hover": { bgcolor: "rgba(255,255,255,0.1)" },
          },
          "& .react-flow__controls button svg": { fill: "rgba(255,255,255,0.6)" },
        }}
      >
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.15, maxZoom: 1 }}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          panOnDrag={true}
          zoomOnScroll={false}
          zoomOnPinch={true}
          preventScrolling={false}
          proOptions={{ hideAttribution: true }}
          colorMode="dark"
        >
          <Background color="rgba(255,255,255,0.03)" gap={20} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </Box>
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function KnowledgeGraph() {
  const [data, setData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [clearing, setClearing] = useState(false);
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchGraph = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiUrl}/graph`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = (await res.json()) as GraphData;
      setData(json);
      setLastUpdated(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load graph");
    } finally {
      setLoading(false);
    }
  }, [apiUrl]);

  async function clearDemoData() {
    setClearing(true);
    try {
      await fetch(`${apiUrl}/graph/demo`, { method: "DELETE" });
      await fetchGraph();
    } finally {
      setClearing(false);
    }
  }

  useEffect(() => {
    fetchGraph();
    intervalRef.current = setInterval(fetchGraph, 30_000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [fetchGraph]);

  const internalCount = data?.developers.length ?? 0;
  const externalCount = data?.upstream_authors?.length ?? 0;
  const moduleCount = data?.modules.filter((m) => (m.contributors?.length ?? 0) > 0).length ?? 0;
  const concentratedCount = data?.concentrated_modules?.length ?? 0;
  const recentFindings: Finding[] = data?.recent_findings ?? [];
  const hasGraph = moduleCount > 0;
  const demoDevCount = data?.developers.filter((d) => d.demo).length ?? 0;
  const demoModCount = data?.modules.filter((m) => m.demo || m.contributors?.some((c) => c.demo)).length ?? 0;
  const hasDemo = demoDevCount > 0 || demoModCount > 0;

  return (
    <Stack spacing={3}>
      {/* Header */}
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center" }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
          <HubOutlinedIcon sx={{ fontSize: 18, color: "primary.light" }} />
          <Typography variant="subtitle2" color="text.secondary">Knowledge Graph</Typography>
          {lastUpdated && (
            <Typography variant="caption" color="text.disabled">
              updated {lastUpdated.toLocaleTimeString()}
            </Typography>
          )}
        </Stack>
        <Stack direction="row" spacing={1}>
          {hasDemo && (
            <Button
              size="small"
              variant="outlined"
              onClick={clearDemoData}
              disabled={clearing}
              startIcon={<DeleteOutlineIcon />}
              sx={{ height: 30, color: "#a78bfa", borderColor: "#7c3aed55", "&:hover": { borderColor: "#a78bfa", bgcolor: "#7c3aed11" } }}
            >
              {clearing ? "Clearing…" : "Clear demo data"}
            </Button>
          )}
          <Button size="small" variant="outlined" onClick={fetchGraph} disabled={loading} startIcon={<RefreshIcon />} sx={{ height: 30 }}>
            {loading ? "Loading…" : "Refresh"}
          </Button>
        </Stack>
      </Stack>

      {/* Demo data banner */}
      {hasDemo && (
        <Paper elevation={0} sx={{ p: 1.5, bgcolor: "#7c3aed11", border: "1px solid #7c3aed44", borderRadius: 2 }}>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
            <ScienceOutlinedIcon sx={{ fontSize: 15, color: "#a78bfa", flexShrink: 0 }} />
            <Typography variant="caption" sx={{ color: "#a78bfa", flex: 1 }}>
              Demo data active — {demoDevCount > 0 ? `${demoDevCount} developer${demoDevCount !== 1 ? "s" : ""}` : ""}
              {demoDevCount > 0 && demoModCount > 0 ? " · " : ""}
              {demoModCount > 0 ? `${demoModCount} module${demoModCount !== 1 ? "s" : ""}` : ""} seeded for simulation.
              Results shown include synthetic entries. Use <strong>Clear demo data</strong> to remove them.
            </Typography>
          </Stack>
        </Paper>
      )}

      {error && <Typography variant="body2" color="error.main">{error}</Typography>}

      {/* Summary cards */}
      <Grid container spacing={2}>
        {[
          { label: "Internal Developers", value: internalCount, icon: <PersonOutlineOutlinedIcon sx={{ fontSize: 16, color: "#4285f4" }} /> },
          { label: "Upstream Authors", value: externalCount, icon: <PersonOutlineOutlinedIcon sx={{ fontSize: 16, color: "#fa7b17" }} />, highlight: externalCount > 0 },
          { label: "Modules Mapped", value: moduleCount, icon: <AccountTreeOutlinedIcon sx={{ fontSize: 16, color: "text.secondary" }} /> },
          { label: "Concentrated (bus≤1)", value: concentratedCount, icon: <WarningAmberOutlinedIcon sx={{ fontSize: 16, color: concentratedCount > 0 ? "#fa7b17" : "text.secondary" }} />, highlight: concentratedCount > 0 },
        ].map(({ label, value, highlight, icon }) => (
          <Grid key={label} size={3}>
            <Paper elevation={0} sx={{ p: 2, bgcolor: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 2 }}>
              <Stack direction="row" spacing={0.75} sx={{ alignItems: "center", mb: 0.5 }}>
                {icon}
                <Typography variant="caption" color="text.secondary">{label}</Typography>
              </Stack>
              <Typography variant="h5" sx={{ fontWeight: 600, color: highlight ? "error.main" : "text.primary" }}>
                {value}
              </Typography>
            </Paper>
          </Grid>
        ))}
      </Grid>

      {!hasGraph && !loading && (
        <Paper elevation={0} sx={{ p: 3, textAlign: "center" }}>
          <Typography variant="body2" color="text.disabled">
            Graph is empty — run the pipeline to populate per-module knowledge data.
          </Typography>
        </Paper>
      )}

      {hasGraph && (
        <>
          {/* Primary: module knowledge breakdown */}
          <Paper elevation={0} sx={{ p: 2.5 }}>
            <Stack direction="row" spacing={1} sx={{ alignItems: "baseline", mb: 2 }}>
              <Typography variant="subtitle2" color="text.secondary">Module Knowledge Breakdown</Typography>
              <Typography variant="caption" color="text.disabled">
                who knows what · sorted by concentration · score = relative commit share (1.0 = top contributor)
              </Typography>
            </Stack>
            <ModuleBreakdown modules={data!.modules} findings={recentFindings} />
          </Paper>

          {/* Secondary: React Flow structural overview + upstream authors */}
          <Grid container spacing={2}>
            <Grid size={7}>
              <Paper elevation={0} sx={{ p: 2.5, height: "100%" }}>
                <Stack direction="row" spacing={1} sx={{ alignItems: "baseline", mb: 1.5 }}>
                  <Typography variant="subtitle2" color="text.secondary">Structural Overview</Typography>
                  <Typography variant="caption" color="text.disabled">edge weight = expertise</Typography>
                </Stack>
                <StructuralOverview modules={data!.modules} />
              </Paper>
            </Grid>

            <Grid size={5}>
              <Paper elevation={0} sx={{ p: 2.5, height: "100%", overflow: "hidden" }}>
                <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1 }}>
                  <WarningAmberOutlinedIcon sx={{ fontSize: 15, color: "warning.main" }} />
                  <Typography variant="subtitle2" color="text.secondary">Upstream Authors</Typography>
                  <Chip label="dark knowledge" size="small" color="warning" variant="outlined" sx={{ height: 18, fontSize: "0.6rem", ml: "auto !important" }} />
                </Stack>
                <Typography variant="caption" color="text.disabled" sx={{ display: "block", mb: 1.5, lineHeight: 1.5 }}>
                  Wrote the code but are not current members. Their knowledge lives only in commit history.
                </Typography>
                {externalCount === 0 ? (
                  <Typography variant="body2" color="text.disabled">None tracked yet</Typography>
                ) : (
                  <UpstreamAuthorList authors={data!.upstream_authors} modules={data!.modules} />
                )}
              </Paper>
            </Grid>
          </Grid>
        </>
      )}
    </Stack>
  );
}
