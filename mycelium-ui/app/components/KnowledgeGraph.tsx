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
};

type Module = {
  path: string;
  owners: string[];
  continuity_risk_score: number;
  bus_factor: number;
  contributors: Contributor[];
};

type Developer = {
  username: string;
  name: string;
  active: boolean;
  external: boolean;
};

type GraphData = {
  developers: Developer[];
  upstream_authors: Developer[];
  modules: Module[];
  high_risk_modules: Module[];
};

// ---------------------------------------------------------------------------
// Risk helpers
// ---------------------------------------------------------------------------
function riskLabel(score: number) {
  if (score >= 0.8) return "CRITICAL";
  if (score >= 0.6) return "HIGH";
  if (score >= 0.4) return "MED";
  return "LOW";
}

function riskColor(score: number) {
  if (score >= 0.8) return "#ea4335";
  if (score >= 0.6) return "#fa7b17";
  if (score >= 0.4) return "#fbbc04";
  return "#34a853";
}

// ---------------------------------------------------------------------------
// React Flow — custom node types (defined outside component to avoid re-render)
// ---------------------------------------------------------------------------
function ModuleFlowNode({ data }: { data: Record<string, unknown> }) {
  const score = data.score as number;
  const path = data.path as string;
  const color = riskColor(score);
  return (
    <Box
      sx={{
        px: 1.5,
        py: 0.75,
        bgcolor: color + "18",
        border: `1px solid ${color}55`,
        borderRadius: 1.5,
        minWidth: 130,
        cursor: "default",
        userSelect: "none",
      }}
    >
      <Typography
        sx={{ color, fontFamily: "monospace", fontWeight: 700, fontSize: "0.7rem", display: "block", lineHeight: 1.4 }}
      >
        {path}/
      </Typography>
      <Typography sx={{ color, opacity: 0.7, fontSize: "0.58rem", lineHeight: 1 }}>
        {riskLabel(score)} · {Math.round(score * 100)}%
      </Typography>
      <Handle type="source" position={Position.Right} style={{ background: color, border: "none", width: 7, height: 7 }} />
    </Box>
  );
}

function ContributorFlowNode({ data }: { data: Record<string, unknown> }) {
  const external = data.external as boolean;
  const username = data.username as string;
  const color = external ? "#fa7b17" : "#4285f4";
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
      <Typography sx={{ color, fontFamily: "monospace", fontSize: "0.68rem", lineHeight: 1.5 }}>
        {username}
      </Typography>
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
const MOD_X = 20;
const CTB_X = 460;
const MOD_GAP = 80;
const CTB_GAP = 52;

function buildFlowGraph(modules: Module[]): { nodes: Node[]; edges: Edge[]; height: number } {
  const topModules = [...modules]
    .filter((m) => (m.contributors?.length ?? 0) > 0)
    .sort((a, b) => b.continuity_risk_score - a.continuity_risk_score)
    .slice(0, 8);

  // Collect unique contributors across visible modules, sorted by expertise
  const contribMap = new Map<string, Contributor>();
  for (const mod of topModules) {
    for (const c of mod.contributors ?? []) {
      if (!contribMap.has(c.developer_username)) contribMap.set(c.developer_username, c);
    }
  }
  const visContribs = [...contribMap.values()]
    .sort((a, b) => b.expertise_score - a.expertise_score)
    .slice(0, 18);

  const modTotalH = (topModules.length - 1) * MOD_GAP;
  const ctbTotalH = (visContribs.length - 1) * CTB_GAP;
  const height = Math.max(modTotalH, ctbTotalH) + 100;
  const modStartY = (height - modTotalH) / 2;
  const ctbStartY = (height - ctbTotalH) / 2;

  const nodes: Node[] = [
    ...topModules.map((mod, i) => ({
      id: `mod-${mod.path}`,
      type: "moduleNode" as const,
      position: { x: MOD_X, y: modStartY + i * MOD_GAP },
      data: { path: mod.path, score: mod.continuity_risk_score },
      draggable: false,
    })),
    ...visContribs.map((c, i) => ({
      id: `ctb-${c.developer_username}`,
      type: "contributorNode" as const,
      position: { x: CTB_X, y: ctbStartY + i * CTB_GAP },
      data: { username: c.developer_username, external: c.external },
      draggable: false,
    })),
  ];

  const contribSet = new Set(visContribs.map((c) => c.developer_username));
  const edges: Edge[] = [];
  for (const mod of topModules) {
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
          strokeOpacity: Math.max(0.08, c.expertise_score * 0.55),
        },
        type: "default",
      });
    }
  }

  return { nodes, edges, height };
}

// ---------------------------------------------------------------------------
// Module Knowledge Breakdown — the primary view
// ---------------------------------------------------------------------------
function ModuleBreakdown({ modules }: { modules: Module[] }) {
  // Detect if data is still in the seeding-only state (only "repository" exists)
  const hasOnlyRoot = modules.length <= 1 && modules[0]?.path === "repository";

  const sorted = [...modules]
    .filter((m) => (m.contributors?.length ?? 0) > 0)
    .sort((a, b) => b.continuity_risk_score - a.continuity_risk_score)
    .slice(0, 12);

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
        const score = mod.continuity_risk_score ?? 0;
        const color = riskColor(score);
        const label = riskLabel(score);
        const contribs = [...(mod.contributors ?? [])].sort((a, b) => b.expertise_score - a.expertise_score);
        const internalCommitters = contribs.filter((c) => !c.external && c.commit_count > 0);
        const noInternalKnowledge = internalCommitters.length === 0 && contribs.length > 0;
        const showTop = contribs.slice(0, 6);
        const hiddenCount = contribs.length - showTop.length;

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
                : score >= 0.6
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
                risk {Math.round(score * 100)}%
              </Typography>
              <Divider orientation="vertical" flexItem sx={{ borderColor: "rgba(255,255,255,0.08)" }} />
              <Typography variant="caption" color="text.disabled" sx={{ flexShrink: 0 }}>
                bus factor {mod.bus_factor ?? 0}
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
                    {c.commit_count > 0 && (
                      <Typography variant="caption" color="text.disabled" sx={{ minWidth: 40, textAlign: "right", flexShrink: 0 }}>
                        {c.commit_count}c
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
    <Stack spacing={1.25} sx={{ maxHeight: 420, overflowY: "auto" }}>
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
              <PersonOutlineOutlinedIcon sx={{ fontSize: 13, color: "#fa7b17", flexShrink: 0 }} />
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="caption" sx={{ fontFamily: "var(--font-google-sans-code)", color: "#fa7b17", display: "block", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {dev.name || dev.username}
                </Typography>
              </Box>
              {totalCommits > 0 && (
                <Typography variant="caption" color="text.disabled" sx={{ flexShrink: 0, fontFamily: "var(--font-google-sans-code)" }}>
                  {totalCommits}c
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
                    <Typography variant="caption" sx={{ fontFamily: "var(--font-google-sans-code)", color: "rgba(250,123,23,0.6)", fontSize: "0.6rem", minWidth: 24, textAlign: "right", flexShrink: 0 }}>
                      {m.commit_count}c
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
  const { nodes, edges, height } = useMemo(() => buildFlowGraph(modules), [modules]);

  if (nodes.length === 0) return null;

  return (
    <Box
      sx={{
        height,
        minHeight: 300,
        width: "100%",
        borderRadius: 2,
        overflow: "hidden",
        "& .react-flow__background": { bgcolor: "transparent" },
        "& .react-flow__controls button": { bgcolor: "rgba(255,255,255,0.06)", border: "1px solid rgba(255,255,255,0.1)", color: "rgba(255,255,255,0.6)", "&:hover": { bgcolor: "rgba(255,255,255,0.1)" } },
        "& .react-flow__controls button svg": { fill: "rgba(255,255,255,0.6)" },
      }}
    >
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
        panOnDrag={false}
        zoomOnScroll={false}
        zoomOnPinch={false}
        preventScrolling={false}
        proOptions={{ hideAttribution: true }}
        colorMode="dark"
      >
        <Background color="rgba(255,255,255,0.04)" gap={20} />
        <Controls showInteractive={false} />
      </ReactFlow>
    </Box>
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

  useEffect(() => {
    fetchGraph();
    intervalRef.current = setInterval(fetchGraph, 30_000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [fetchGraph]);

  const internalCount = data?.developers.length ?? 0;
  const externalCount = data?.upstream_authors?.length ?? 0;
  const moduleCount = data?.modules.filter((m) => (m.contributors?.length ?? 0) > 0).length ?? 0;
  const highRiskCount = data?.high_risk_modules.length ?? 0;
  const hasGraph = moduleCount > 0;

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
        <Button size="small" variant="outlined" onClick={fetchGraph} disabled={loading} startIcon={<RefreshIcon />} sx={{ height: 30 }}>
          {loading ? "Loading…" : "Refresh"}
        </Button>
      </Stack>

      {error && <Typography variant="body2" color="error.main">{error}</Typography>}

      {/* Summary cards */}
      <Grid container spacing={2}>
        {[
          { label: "Internal Developers", value: internalCount, icon: <PersonOutlineOutlinedIcon sx={{ fontSize: 16, color: "#4285f4" }} /> },
          { label: "Upstream Authors", value: externalCount, icon: <PersonOutlineOutlinedIcon sx={{ fontSize: 16, color: "#fa7b17" }} />, highlight: externalCount > 0 },
          { label: "Modules Mapped", value: moduleCount, icon: <AccountTreeOutlinedIcon sx={{ fontSize: 16, color: "text.secondary" }} /> },
          { label: "High-Risk Modules", value: highRiskCount, icon: <WarningAmberOutlinedIcon sx={{ fontSize: 16, color: highRiskCount > 0 ? "#ea4335" : "text.secondary" }} />, highlight: highRiskCount > 0 },
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
                who knows what · sorted by risk
              </Typography>
            </Stack>
            <ModuleBreakdown modules={data!.modules} />
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
              <Paper elevation={0} sx={{ p: 2.5, height: "100%" }}>
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
