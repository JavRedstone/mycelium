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
import Drawer from "@mui/material/Drawer";
import IconButton from "@mui/material/IconButton";
import Tooltip from "@mui/material/Tooltip";
import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";
import ListItemText from "@mui/material/ListItemText";
import ListItemIcon from "@mui/material/ListItemIcon";
import RefreshIcon from "@mui/icons-material/Refresh";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutlined";
import ScienceOutlinedIcon from "@mui/icons-material/ScienceOutlined";
import HubOutlinedIcon from "@mui/icons-material/HubOutlined";
import WarningAmberOutlinedIcon from "@mui/icons-material/WarningAmberOutlined";
import PersonOutlineOutlinedIcon from "@mui/icons-material/PersonOutlineOutlined";
import AccountTreeOutlinedIcon from "@mui/icons-material/AccountTreeOutlined";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import CloseIcon from "@mui/icons-material/Close";
import CallSplitOutlinedIcon from "@mui/icons-material/CallSplitOutlined";
import StarOutlinedIcon from "@mui/icons-material/StarOutlined";
import ChevronRightOutlinedIcon from "@mui/icons-material/ChevronRightOutlined";
import FiberManualRecordIcon from "@mui/icons-material/FiberManualRecord";
import AddCircleOutlinedIcon from "@mui/icons-material/AddCircleOutlined";
import ArrowDropDownIcon from "@mui/icons-material/ArrowDropDown";

import { filterModules, isBotUsername } from "../lib/graphFilters";

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

type BusfactorEntry = {
  username: string;
  expertise_score: number;
  share_pct: number;
  cumulative_pct: number;
  in_bus_factor: boolean;
  commit_count: number;
  external?: boolean;
};

type BusfactorModule = {
  module_path: string;
  bus_factor: number;
  dev_expertise_score: number;
  dev_share_pct: number;
  dev_commit_count: number;
  total_commit_count: number;
  dev_in_bus_factor: boolean;
  total_internal_contributors: number;
  total_external_contributors: number;
  breakdown: BusfactorEntry[];
};

type BusfactorData = {
  username: string;
  name: string;
  external: boolean;
  demo: boolean;
  modules: BusfactorModule[];
};

// ---------------------------------------------------------------------------
// Bus-factor drawer — shown when a developer name is clicked
// ---------------------------------------------------------------------------
function BusfactorDrawer({
  username,
  open,
  onClose,
  apiUrl,
}: {
  username: string | null;
  open: boolean;
  onClose: () => void;
  apiUrl: string;
}) {
  const [data, setData] = useState<BusfactorData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open || !username) { setData(null); return; }
    // Namespace-style usernames (e.g. "gitlab-org/maintainers/gitlab-pages") are GitLab
    // service accounts from upstream fork history. The backend rejects them with 400.
    // Catch this early on the client so the user sees a clear message, not a raw HTTP error.
    if (username.includes("/")) {
      setData(null);
      setError("This entry is a GitLab service account or namespace path from upstream fork history, not a real contributor. It has no individual bus-factor breakdown.");
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    fetch(`${apiUrl}/developers/busfactor?username=${encodeURIComponent(username)}`)
      .then((r) => { if (!r.ok) throw new Error(`HTTP ${r.status}`); return r.json(); })
      .then((d) => setData(d as BusfactorData))
      .catch((e) => setError(e instanceof Error ? e.message : "Failed to load"))
      .finally(() => setLoading(false));
  }, [open, username, apiUrl]);

  const BAR_WIDTH = 160; // px for the share bar

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      slotProps={{
        paper: {
          sx: {
            width: 520,
            bgcolor: "background.default",
            borderLeft: "1px solid rgba(255,255,255,0.08)",
            p: 0,
          },
        },
      }}
    >
      {/* Header */}
      <Box sx={{ px: 2.5, py: 2, borderBottom: "1px solid rgba(255,255,255,0.07)", display: "flex", alignItems: "center", gap: 1 }}>
        <CallSplitOutlinedIcon sx={{ fontSize: 16, color: "primary.light", flexShrink: 0 }} />
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="subtitle2" sx={{ fontFamily: "var(--font-google-sans-code)", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {username}
          </Typography>
          {data && (
            <Typography variant="caption" color="text.disabled">
              {data.name !== username ? data.name + " · " : ""}
              {data.external ? "upstream author · dark knowledge view" : "bus-factor impact"}
              {data.demo ? " · demo" : ""}
            </Typography>
          )}
        </Box>
        <IconButton size="small" onClick={onClose} sx={{ color: "text.disabled" }}>
          <CloseIcon sx={{ fontSize: 16 }} />
        </IconButton>
      </Box>

      <Box sx={{ px: 2.5, py: 2, overflowY: "auto", height: "calc(100vh - 72px)" }}>
        {loading && <LinearProgress sx={{ borderRadius: 1, mb: 2 }} />}
        {error && <Typography variant="body2" color="error.main">{error}</Typography>}

        {data && !loading && (
          <>
            {/* Context banner — different for upstream vs internal */}
            {data.external ? (
              <Paper elevation={0} sx={{ p: 1.5, mb: 2.5, bgcolor: "rgba(250,123,23,0.06)", border: "1px solid rgba(250,123,23,0.2)", borderRadius: 1.5 }}>
                <Stack direction="row" spacing={1} sx={{ alignItems: "flex-start" }}>
                  <WarningAmberOutlinedIcon sx={{ fontSize: 13, color: "#fa7b17", flexShrink: 0, mt: 0.25 }} />
                  <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.6 }}>
                    <strong>Upstream author</strong>: not a current project member.
                    Their commits are <strong>excluded from bus-factor calculations</strong> because they cannot transfer knowledge to the team.
                    Bars show their share of <em>all</em> commits to each module (internal + upstream combined).
                    The team members who do hold each module are listed below each bar.
                  </Typography>
                </Stack>
              </Paper>
            ) : (
              <Paper elevation={0} sx={{ p: 1.5, mb: 2.5, bgcolor: "rgba(66,133,244,0.06)", border: "1px solid rgba(66,133,244,0.15)", borderRadius: 1.5 }}>
                <Stack direction="row" spacing={1} sx={{ alignItems: "flex-start" }}>
                  <InfoOutlinedIcon sx={{ fontSize: 13, color: "primary.light", flexShrink: 0, mt: 0.25 }} />
                  <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.6 }}>
                    <strong>Bus factor</strong> = minimum internal contributors (by expertise) covering ≥80% of a module.
                    Rows marked <StarOutlinedIcon sx={{ fontSize: 10, color: "#4285f4", verticalAlign: "middle", mx: 0.25 }} /> are inside that 80% threshold. Losing them drops coverage below 80%.
                    Bars show each person&apos;s share of internal expertise for that module.
                  </Typography>
                </Stack>
              </Paper>
            )}

            {data.modules.length === 0 && (
              <Typography variant="body2" color="text.disabled">
                No module contributions recorded yet.
              </Typography>
            )}

            {data.modules.length > 0 && (
              <>
                {/* Section heading */}
                <Box sx={{ mb: 1.5 }}>
                  <Typography variant="caption" color="text.secondary" sx={{ fontWeight: 600, display: "block" }}>
                    {data.modules.length} module{data.modules.length !== 1 ? "s" : ""} where {username} has contributed
                  </Typography>
                  <Typography variant="caption" color="text.disabled" sx={{ display: "block", mt: 0.25 }}>
                    Score is normalized per module: top contributor = 1.00. Same scale as the main graph.
                  </Typography>
                </Box>

                <Stack spacing={2}>
                  {data.modules.map((mod) => {
                    const inBus = mod.dev_in_bus_factor;
                    const isUpstream = data.external;
                    const accentColor = isUpstream ? "#fa7b17" : inBus ? "#fa7b17" : "#4285f4";
                    const busColor = mod.bus_factor === 0 ? "#ea4335" : mod.bus_factor === 1 ? "#fa7b17" : mod.bus_factor === 2 ? "#fbbc04" : "#34a853";
                    const noInternal = mod.total_internal_contributors === 0;

                    // Pre-compute internal breakdown sorted by expertise (bus-factor ordering)
                    // with absolute percentages based on internal commit counts only.
                    // Also filter out bot/namespace-path entries that slipped through (username
                    // contains "/" from pre-fix runs, or known bot segments like "maintainers").
                    const _botSegments = ["maintainers", "gitlab-org", "gitlab_org", "noreply"];
                    const _isBotUsername = (u: string) =>
                      u.includes("/") || _botSegments.some((s) => u.toLowerCase().includes(s));
                    const internalRows = mod.breakdown
                      .filter((b) => !b.external && !_isBotUsername(b.username))
                      .sort((a, b) => b.expertise_score - a.expertise_score);
                    const internalCommitTotal = internalRows.reduce((s, b) => s + (b.commit_count ?? 0), 0);
                    const topInternalRows = internalRows.slice(0, 8);
                    const hiddenInternalCount = internalRows.length - topInternalRows.length;
                    let _cumAcc = 0;
                    const rowsWithCum = topInternalRows.map((b) => {
                      const pct = internalCommitTotal > 0 ? ((b.commit_count ?? 0) / internalCommitTotal) * 100 : 0;
                      _cumAcc += pct;
                      return { b, pct, cumPct: _cumAcc };
                    });

                    return (
                      <Paper
                        key={mod.module_path}
                        elevation={0}
                        sx={{
                          p: 1.75,
                          bgcolor: "rgba(255,255,255,0.02)",
                          border: "1px solid",
                          borderColor: isUpstream
                            ? "rgba(250,123,23,0.15)"
                            : inBus ? "rgba(250,123,23,0.22)" : "rgba(255,255,255,0.06)",
                          borderRadius: 2,
                        }}
                      >
                        {/* Module path + bus-factor chips */}
                        <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 1, flexWrap: "wrap" }} useFlexGap>
                          {!isUpstream && (
                            <Chip
                              label={`bus ${mod.bus_factor}`}
                              size="small"
                              sx={{ bgcolor: busColor + "18", color: busColor, border: `1px solid ${busColor}44`, height: 18, fontSize: "0.6rem", fontWeight: 700, flexShrink: 0 }}
                            />
                          )}
                          <Typography
                            variant="body2"
                            sx={{ fontFamily: "var(--font-google-sans-code)", fontWeight: 600, flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}
                          >
                            {mod.module_path}/
                          </Typography>
                          {!isUpstream && inBus && (
                            <Tooltip title={`${username} is inside the 80% threshold. Their departure reduces this module's internal coverage below 80%.`}>
                              <Chip
                                label="in threshold"
                                size="small"
                                icon={<WarningAmberOutlinedIcon sx={{ fontSize: "10px !important" }} />}
                                sx={{ height: 18, fontSize: "0.6rem", flexShrink: 0, color: "#fa7b17", borderColor: "#fa7b1744", bgcolor: "#fa7b1711", border: "1px solid" }}
                              />
                            </Tooltip>
                          )}
                        </Stack>

                        {/* Breakdown: always shows internal team with bus-factor context.
                            For upstream author drawers this answers "who on the team holds this?" */}
                        {noInternal ? (
                          <Typography variant="caption" color="text.disabled" sx={{ pl: "22px", display: "block" }}>
                            {isUpstream
                              ? "No internal contributors — entirely upstream knowledge for this module."
                              : "No internal contributors. All knowledge is upstream."}
                          </Typography>
                        ) : (
                          <Stack spacing={0.5}>
                            <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.58rem", textTransform: "uppercase", letterSpacing: "0.06em", mb: 0.25 }}>
                              {isUpstream ? "Team members who hold this module" : "Internal contributors"}
                              {" (★ inside 80% threshold)"}
                            </Typography>

                            {rowsWithCum.map(({ b, pct, cumPct }) => {
                              const isSubject = !isUpstream && b.username === username;
                              const bColor = isSubject && inBus ? "#fa7b17" : "#4285f4";
                              const rowColor = isSubject ? bColor : b.in_bus_factor ? "#4285f4" : "rgba(255,255,255,0.45)";
                              const barColor = isSubject ? bColor : b.in_bus_factor ? "rgba(66,133,244,0.6)" : "rgba(255,255,255,0.18)";
                              return (
                                <Stack key={b.username} direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
                                  <Box sx={{ minWidth: 14, flexShrink: 0, display: "flex", alignItems: "center" }}>
                                    {isSubject
                                      ? <ChevronRightOutlinedIcon sx={{ fontSize: 12, color: bColor }} />
                                      : b.in_bus_factor
                                      ? <StarOutlinedIcon sx={{ fontSize: 11, color: "#4285f4" }} />
                                      : <FiberManualRecordIcon sx={{ fontSize: 5, color: "rgba(255,255,255,0.15)" }} />
                                    }
                                  </Box>
                                  <Typography
                                    variant="caption"
                                    sx={{
                                      fontFamily: "var(--font-google-sans-code)",
                                      color: rowColor,
                                      fontWeight: isSubject ? 700 : 400,
                                      minWidth: 110,
                                      maxWidth: 110,
                                      overflow: "hidden",
                                      textOverflow: "ellipsis",
                                      whiteSpace: "nowrap",
                                      flexShrink: 0,
                                    }}
                                  >
                                    {b.username}
                                  </Typography>
                                  <Box sx={{ flex: 1, minWidth: 50, position: "relative" }}>
                                    <Box sx={{ height: 4, borderRadius: 2, bgcolor: "rgba(255,255,255,0.05)", overflow: "hidden" }}>
                                      <Box sx={{ height: "100%", width: `${Math.min(100, pct)}%`, bgcolor: barColor, borderRadius: 2, transition: "width 0.3s ease" }} />
                                    </Box>
                                    <Box sx={{ position: "absolute", top: 0, left: "80%", height: "100%", width: "1px", bgcolor: "rgba(255,255,255,0.18)", pointerEvents: "none" }} />
                                  </Box>
                                  <Typography
                                    variant="caption"
                                    sx={{ fontFamily: "var(--font-google-sans-code)", color: rowColor, minWidth: 34, textAlign: "right", flexShrink: 0 }}
                                  >
                                    {pct.toFixed(1)}%
                                  </Typography>
                                  <Typography variant="caption" color="text.disabled" sx={{ minWidth: 58, textAlign: "right", flexShrink: 0, fontFamily: "var(--font-google-sans-code)" }}>
                                    {cumPct.toFixed(0)}% running
                                  </Typography>
                                </Stack>
                              );
                            })}

                            {hiddenInternalCount > 0 && (
                              <Typography variant="caption" color="text.disabled" sx={{ pl: "22px", fontSize: "0.6rem" }}>
                                +{hiddenInternalCount} more internal contributors
                              </Typography>
                            )}

                            {isUpstream && (
                              <Typography variant="caption" sx={{ pl: "22px", display: "block", color: "rgba(250,123,23,0.7)", fontSize: "0.6rem", mt: 0.25 }}>
                                {username} is upstream — not counted in team bus factor
                              </Typography>
                            )}

                            {/* Footer */}
                            <Box sx={{ pl: "22px", mt: 0.25 }}>
                              <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.58rem" }}>
                                {mod.total_internal_contributors} internal contributor{mod.total_internal_contributors !== 1 ? "s" : ""}
                                {mod.bus_factor > 0
                                  ? ` · ${mod.bus_factor} cover${mod.bus_factor === 1 ? "s" : ""} ≥80%`
                                  : " · no internal coverage"}
                                {mod.total_external_contributors > 0
                                  ? ` · ${mod.total_external_contributors} upstream`
                                  : ""}
                              </Typography>
                            </Box>
                          </Stack>
                        )}
                      </Paper>
                    );
                  })}
                </Stack>
              </>
            )}
          </>
        )}
      </Box>
    </Drawer>
  );
}

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
    .filter((m) => (m.contributors?.length ?? 0) > 0 && m.path !== "repository")
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
// Bus-factor breakdown rows — "who covers ≥80%" view per module card
// ---------------------------------------------------------------------------
function BusfactorModuleRows({
  contribs,
  internalCommitTotal,
  onSelectDev,
}: {
  contribs: Contributor[];
  internalCommitTotal: number;
  onSelectDev?: (username: string) => void;
}) {
  const internal = [...contribs.filter((c) => !c.external)].sort(
    (a, b) => b.expertise_score - a.expertise_score,
  );
  const external = contribs.filter((c) => c.external);

  // Compute 80% expertise threshold (same logic as backend compute_bus_factor).
  const expertiseTotal = internal.reduce((s, c) => s + c.expertise_score, 0);
  let cumExp = 0;
  let thresholdDone = false;
  const rows = internal.map((c) => {
    if (thresholdDone) return { ...c, inBF: false };
    cumExp += c.expertise_score;
    const inBF = true;
    if (expertiseTotal > 0 && cumExp / expertiseTotal >= 0.8) thresholdDone = true;
    return { ...c, inBF };
  });

  const inThreshold = rows.filter((r) => r.inBF);
  const below = rows.filter((r) => !r.inBF);

  const nameStyle = (clickable: boolean, dim = false) => ({
    fontFamily: "var(--font-google-sans-code)",
    color: dim ? "rgba(66,133,244,0.5)" : "#4285f4",
    minWidth: 140,
    maxWidth: 140,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    flexShrink: 0,
    cursor: clickable ? "pointer" : "default",
    textDecoration: clickable ? "underline dotted" : "none",
    textDecorationColor: dim ? "rgba(66,133,244,0.3)" : "rgba(66,133,244,0.4)",
    "&:hover": clickable ? { textDecorationColor: dim ? "rgba(66,133,244,0.6)" : "#4285f4" } : {},
  });

  return (
    <Stack spacing={0.6}>
      {internal.length === 0 && (
        <Typography variant="caption" color="error.main" sx={{ fontSize: "0.68rem" }}>
          No internal contributors — all knowledge held upstream.
        </Typography>
      )}

      {/* Key holders (in threshold) */}
      {inThreshold.length > 0 && (
        <Typography variant="caption" sx={{ fontSize: "0.6rem", textTransform: "uppercase", letterSpacing: "0.07em", color: "rgba(251,188,4,0.7)", display: "block", mb: 0.25 }}>
          ★ covers ≥80% · {inThreshold.length} key holder{inThreshold.length !== 1 ? "s" : ""}
        </Typography>
      )}
      {inThreshold.map((c) => {
        const pct = internalCommitTotal > 0 ? (c.commit_count / internalCommitTotal) * 100 : 0;
        return (
          <Stack key={c.developer_username} direction="row" spacing={1} sx={{ alignItems: "center" }}>
            <StarOutlinedIcon sx={{ fontSize: 11, color: "#fbbc04", flexShrink: 0 }} />
            <Typography variant="caption" onClick={() => onSelectDev?.(c.developer_username)} sx={nameStyle(!!onSelectDev)}>
              {c.developer_username}
            </Typography>
            <Box sx={{ flex: 1, minWidth: 60 }}>
              <LinearProgress variant="determinate" value={Math.min(100, Math.round(pct))}
                sx={{ height: 5, borderRadius: 2, bgcolor: "rgba(255,255,255,0.05)", "& .MuiLinearProgress-bar": { bgcolor: "#fbbc04", borderRadius: 2, opacity: 0.9 } }} />
            </Box>
            <Typography variant="caption" sx={{ fontFamily: "var(--font-google-sans-code)", color: "#fbbc04", minWidth: 38, textAlign: "right", flexShrink: 0, fontSize: "0.7rem" }}>
              {pct.toFixed(1)}%
            </Typography>
            <Typography variant="caption" color="text.disabled" sx={{ minWidth: 48, textAlign: "right", flexShrink: 0, fontSize: "0.65rem" }}>
              {c.commit_count} c
            </Typography>
          </Stack>
        );
      })}

      {/* Separator */}
      {below.length > 0 && (
        <Stack direction="row" spacing={0.75} sx={{ alignItems: "center", py: 0.25 }}>
          <Box sx={{ flex: 1, borderTop: "1px dashed rgba(255,255,255,0.1)" }} />
          <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.58rem", whiteSpace: "nowrap" }}>
            remaining
          </Typography>
          <Box sx={{ flex: 1, borderTop: "1px dashed rgba(255,255,255,0.1)" }} />
        </Stack>
      )}

      {/* Below threshold */}
      {below.map((c) => {
        const pct = internalCommitTotal > 0 ? (c.commit_count / internalCommitTotal) * 100 : 0;
        return (
          <Stack key={c.developer_username} direction="row" spacing={1} sx={{ alignItems: "center" }}>
            <Box sx={{ width: 11, flexShrink: 0 }} />
            <Typography variant="caption" onClick={() => onSelectDev?.(c.developer_username)} sx={nameStyle(!!onSelectDev, true)}>
              {c.developer_username}
            </Typography>
            <Box sx={{ flex: 1, minWidth: 60 }}>
              <LinearProgress variant="determinate" value={Math.min(100, Math.round(pct))}
                sx={{ height: 4, borderRadius: 2, bgcolor: "rgba(255,255,255,0.05)", "& .MuiLinearProgress-bar": { bgcolor: "#4285f4", borderRadius: 2, opacity: 0.4 } }} />
            </Box>
            <Typography variant="caption" sx={{ fontFamily: "var(--font-google-sans-code)", color: "rgba(66,133,244,0.5)", minWidth: 38, textAlign: "right", flexShrink: 0, fontSize: "0.7rem" }}>
              {pct.toFixed(1)}%
            </Typography>
            <Typography variant="caption" color="text.disabled" sx={{ minWidth: 48, textAlign: "right", flexShrink: 0, fontSize: "0.65rem", opacity: 0.6 }}>
              {c.commit_count} c
            </Typography>
          </Stack>
        );
      })}

      {/* Upstream summary */}
      {external.length > 0 && (
        <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.6rem", mt: 0.5, fontStyle: "italic" }}>
          +{external.length} upstream contributor{external.length !== 1 ? "s" : ""} · dark knowledge · excluded from bus factor
        </Typography>
      )}
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Module Knowledge Breakdown — the primary view
// ---------------------------------------------------------------------------
function ModuleBreakdown({
  modules,
  findings,
  onSelectDev,
  demoMode = false,
}: {
  modules: Module[];
  findings: Finding[];
  onSelectDev?: (username: string) => void;
  demoMode?: boolean;
}) {
  const [viewMode, setViewMode] = useState<"score" | "absolute" | "busfactor">("score");

  // Detect if data is still in the seeding-only state (only "repository" exists)
  const hasOnlyRoot = modules.length <= 1 && modules[0]?.path === "repository";

  // Sort by structural concentration (a measurement). Modules with no internal
  // committers float to the top; then by bus_factor ascending.
  // Also filter out namespace-style paths (e.g. "gitlab-org/maintainers/gitlab-pages")
  // that crept in from upstream fork history — real local directories never contain "/".
  const sorted = filterModules(modules)
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
        No module data yet. Run the pipeline to populate per-directory knowledge.
      </Typography>
    );
  }

  return (
    <Stack spacing={1.25}>
      {/* View mode toggle */}
      <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }} useFlexGap>
        <Typography variant="body2" color="text.secondary" sx={{ fontWeight: 500, mr: 0.5 }}>View:</Typography>
        <Button
          size="small"
          variant={viewMode === "score" ? "contained" : "outlined"}
          onClick={() => setViewMode("score")}
          sx={{ height: 32, px: 2, fontSize: "0.75rem", textTransform: "none" }}
        >
          Relative score
        </Button>
        <Button
          size="small"
          variant={viewMode === "absolute" ? "contained" : "outlined"}
          onClick={() => setViewMode("absolute")}
          sx={{ height: 32, px: 2, fontSize: "0.75rem", textTransform: "none" }}
        >
          Absolute %
        </Button>
        <Button
          size="small"
          variant={viewMode === "busfactor" ? "contained" : "outlined"}
          onClick={() => setViewMode("busfactor")}
          sx={{ height: 32, px: 2, fontSize: "0.75rem", textTransform: "none" }}
        >
          Bus factor
        </Button>
        <Typography variant="caption" color="text.disabled" sx={{ alignSelf: "center" }}>
          {viewMode === "score"
            ? "top contributor per module = 1.00"
            : viewMode === "absolute"
            ? "each person's share of module commits"
            : "who covers ≥80% of expertise · key holders vs supporting"}
        </Typography>
      </Stack>

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
        // Filter out namespace-style contributor usernames (GitLab bots / service accounts
        // from upstream fork history, e.g. "gitlab-org/maintainers/gitlab-pages").
        // Real GitLab usernames never contain "/".
        // Filter namespace-path entries, then re-normalize expertise_score so the top
        // *remaining* real contributor = 1.00. Without this, bots / group-path entries
        // (e.g. "gitlab-org/maintainers/gitlab-pages") that dominated the DB normalization
        // make every real contributor appear at ~0% in relative-score mode.
        const _rawContribs = [...(mod.contributors ?? [])]
          .filter((c) => !c.developer_username.includes("/"))
          .sort((a, b) => b.expertise_score - a.expertise_score);
        const _topScore = _rawContribs.length > 0 ? _rawContribs[0].expertise_score : 1;
        const contribs = _rawContribs.map((c) => ({
          ...c,
          expertise_score: _topScore > 0 ? c.expertise_score / _topScore : 0,
        }));
        const moduleCommitTotal = contribs.reduce((s, c) => s + (c.commit_count ?? 0), 0);
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
              <Tooltip
                placement="top"
                title={
                  <Box sx={{ maxWidth: 320, py: 0.5 }}>
                    <Typography variant="caption" sx={{ display: "block", fontWeight: 600, mb: 0.5 }}>
                      Bus factor: a per-module metric
                    </Typography>
                    <Typography variant="caption" sx={{ display: "block", mb: 0.5 }}>
                      Minimum number of <strong>internal</strong> contributors whose
                      combined expertise covers ≥80% of this module. Upstream authors
                      are excluded and cannot transfer knowledge to the team.
                    </Typography>
                    <Typography variant="caption" sx={{ display: "block", color: "rgba(255,255,255,0.6)" }}>
                      <strong>0</strong> = no internal contributors (dark knowledge zone). <strong>1</strong> = one person holds &gt;80% (fragile). Higher = safer.
                    </Typography>
                  </Box>
                }
              >
                <Stack direction="row" spacing={0.5} sx={{ alignItems: "center", flexShrink: 0, cursor: "help" }}>
                  <Typography variant="caption" color="text.disabled">
                    bus factor {busFactor}
                  </Typography>
                  <InfoOutlinedIcon sx={{ fontSize: 11, color: "rgba(255,255,255,0.35)" }} />
                </Stack>
              </Tooltip>
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

            {/* Body — contributions view or bus factor view */}
            {viewMode === "busfactor" ? (
              <BusfactorModuleRows
                contribs={contribs}
                internalCommitTotal={contribs.filter((c) => !c.external).reduce((s, c) => s + (c.commit_count ?? 0), 0)}
                onSelectDev={onSelectDev}
              />
            ) : (
              <Stack spacing={0.6}>
                {/* Column header row */}
                {showTop.length > 0 && (
                  <Stack direction="row" spacing={1} sx={{ alignItems: "center", pb: 0.75, mb: 0.1, borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                    <Box sx={{ minWidth: 14, flexShrink: 0 }} />
                    <Typography sx={{ minWidth: 130, maxWidth: 130, fontSize: "0.56rem", color: "rgba(255,255,255,0.22)", textTransform: "uppercase", letterSpacing: "0.07em", flexShrink: 0 }}>
                      contributor
                    </Typography>
                    <Box sx={{ flex: 1, minWidth: 60 }}>
                      <Typography sx={{ fontSize: "0.56rem", color: "rgba(255,255,255,0.22)", textTransform: "uppercase", letterSpacing: "0.07em" }}>
                        expertise
                      </Typography>
                    </Box>
                    <Typography sx={{ minWidth: 32, textAlign: "right", fontSize: "0.56rem", color: "rgba(255,255,255,0.22)", textTransform: "uppercase", letterSpacing: "0.07em", flexShrink: 0 }}>
                      {viewMode === "score" ? "score" : "%"}
                    </Typography>
                    <Typography sx={{ minWidth: 58, textAlign: "center", fontSize: "0.56rem", color: "rgba(255,255,255,0.22)", textTransform: "uppercase", letterSpacing: "0.07em", flexShrink: 0 }}>
                      type
                    </Typography>
                    <Typography sx={{ minWidth: 60, textAlign: "right", fontSize: "0.56rem", color: "rgba(255,255,255,0.22)", textTransform: "uppercase", letterSpacing: "0.07em", flexShrink: 0 }}>
                      commits
                    </Typography>
                  </Stack>
                )}

                {showTop.map((c, i) => {
                  const contribColor = c.external ? "#fa7b17" : "#4285f4";
                  const isDemoRow = c.demo && demoMode;
                  return (
                    <Stack key={c.developer_username} direction="row" spacing={1} sx={{ alignItems: "center" }}>
                      <Box sx={{ minWidth: 14, flexShrink: 0, display: "flex", alignItems: "center" }}>
                        {isDemoRow
                          ? <ScienceOutlinedIcon sx={{ fontSize: 11, color: "#a78bfa" }} />
                          : i === 0
                          ? <ChevronRightOutlinedIcon sx={{ fontSize: 13, color: contribColor }} />
                          : <FiberManualRecordIcon sx={{ fontSize: 5, color: "rgba(255,255,255,0.2)" }} />
                        }
                      </Box>
                      <Tooltip
                        title={c.external
                          ? `View upstream knowledge breakdown for ${c.developer_username}`
                          : `View bus-factor impact for ${c.developer_username}`}
                        placement="top"
                      >
                        <Typography
                          variant="caption"
                          onClick={() => onSelectDev?.(c.developer_username)}
                          sx={{
                            fontFamily: "var(--font-google-sans-code)",
                            color: contribColor,
                            minWidth: 130,
                            maxWidth: 130,
                            overflow: "hidden",
                            textOverflow: "ellipsis",
                            whiteSpace: "nowrap",
                            flexShrink: 0,
                            cursor: onSelectDev ? "pointer" : "default",
                            textDecoration: onSelectDev ? "underline dotted" : "none",
                            textDecorationColor: contribColor + "66",
                            "&:hover": onSelectDev ? { textDecorationColor: contribColor } : {},
                          }}
                        >
                          {c.developer_username}
                        </Typography>
                      </Tooltip>
                      <Box sx={{ flex: 1, minWidth: 60 }}>
                        <LinearProgress
                          variant="determinate"
                          value={viewMode === "score"
                            ? Math.round(c.expertise_score * 100)
                            : moduleCommitTotal > 0 ? Math.round((c.commit_count / moduleCommitTotal) * 100) : 0}
                          sx={{
                            height: 4, borderRadius: 2, bgcolor: "rgba(255,255,255,0.05)",
                            "& .MuiLinearProgress-bar": { bgcolor: contribColor, borderRadius: 2, opacity: 0.85 },
                          }}
                        />
                      </Box>
                      <Tooltip
                        placement="top"
                        title={
                          viewMode === "score" ? (
                            <Box sx={{ maxWidth: 280, py: 0.5 }}>
                              <Typography variant="caption" sx={{ display: "block", fontWeight: 600, mb: 0.5 }}>
                                Expertise score: {c.expertise_score.toFixed(2)}
                              </Typography>
                              <Typography variant="caption" sx={{ display: "block" }}>
                                Normalized so the top contributor = <strong>1.00</strong>. So 0.50 means about half as many commits as the top contributor in {mod.path}/.
                              </Typography>
                            </Box>
                          ) : (
                            <Box sx={{ maxWidth: 280, py: 0.5 }}>
                              <Typography variant="caption" sx={{ display: "block", fontWeight: 600, mb: 0.5 }}>
                                Commit share: {moduleCommitTotal > 0 ? ((c.commit_count / moduleCommitTotal) * 100).toFixed(1) : 0}%
                              </Typography>
                              <Typography variant="caption" sx={{ display: "block" }}>
                                {c.commit_count} of {moduleCommitTotal} recorded commits to {mod.path}/.
                              </Typography>
                            </Box>
                          )
                        }
                      >
                        <Typography
                          variant="caption"
                          sx={{ fontFamily: "var(--font-google-sans-code)", color: contribColor, minWidth: 32, textAlign: "right", flexShrink: 0, cursor: "help" }}
                        >
                          {viewMode === "score"
                            ? c.expertise_score.toFixed(2)
                            : moduleCommitTotal > 0 ? `${((c.commit_count / moduleCommitTotal) * 100).toFixed(1)}%` : "—"}
                        </Typography>
                      </Tooltip>
                      <Chip
                        label={c.external ? "upstream" : "internal"}
                        size="small"
                        variant="outlined"
                        sx={{ height: 16, fontSize: "0.58rem", minWidth: 58, flexShrink: 0, color: contribColor, borderColor: contribColor + "44" }}
                      />
                      {c.demo && !demoMode && (
                        <Chip
                          label="demo"
                          size="small"
                          sx={{ height: 16, fontSize: "0.58rem", flexShrink: 0, color: "#a78bfa", bgcolor: "#7c3aed11", border: "1px solid #7c3aed55" }}
                        />
                      )}
                      {c.commit_count > 0 && (
                        <Typography variant="caption" color="text.disabled" sx={{ minWidth: 60, textAlign: "right", flexShrink: 0 }}>
                          {c.commit_count} commit{c.commit_count !== 1 ? "s" : ""}
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
            )}
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
                  {totalCommits} commit{totalCommits !== 1 ? "s" : ""}
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
                      {m.commit_count} commit{m.commit_count !== 1 ? "s" : ""}
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
// ---------------------------------------------------------------------------
// Scenario metadata
// ---------------------------------------------------------------------------
const SCENARIOS = [
  {
    id: "team",
    label: "Full team",
    description: "Alex Chen, Priya Sharma, Marco Torres + full module coverage",
  },
  {
    id: "new_joiner",
    label: "New joiner",
    description: "Marco Torres: joined 2 weeks ago, 1 test commit → onboarding pack",
  },
  {
    id: "fading",
    label: "Fading contributor",
    description: "Priya Sharma: sole scripts/ owner, 6 months inactive → offboarding",
  },
  {
    id: "sole_owner",
    label: "Sole owner",
    description: "Alex Chen: sole holder of app/ and internal/ → knowledge transfer issue",
  },
] as const;

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function KnowledgeGraph() {
  const [data, setData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(false);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [demoMode, setDemoMode] = useState<boolean>(false);
  const [clearing, setClearing] = useState(false);
  const [seeding, setSeeding] = useState(false);
  const [seedMenuAnchor, setSeedMenuAnchor] = useState<null | HTMLElement>(null);
  const [selectedDev, setSelectedDev] = useState<string | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  function openDevDrawer(username: string) {
    setSelectedDev(username);
    setDrawerOpen(true);
  }

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

  // Fetch demo_mode from /config once on mount
  useEffect(() => {
    fetch(`${apiUrl}/config`)
      .then((r) => r.json())
      .then((cfg: Record<string, unknown>) => setDemoMode(cfg.demo_mode === true))
      .catch(() => {/* silently ignore — demo controls stay hidden */});
  }, [apiUrl]);

  async function clearDemoData() {
    setClearing(true);
    try {
      const res = await fetch(`${apiUrl}/graph/demo`, { method: "DELETE" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await fetchGraph();
    } finally {
      setClearing(false);
    }
  }

  async function seedScenario(scenario: string) {
    setSeedMenuAnchor(null);
    setSeeding(true);
    try {
      const res = await fetch(`${apiUrl}/demo/seed/${scenario}`, { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      await fetchGraph();
    } finally {
      setSeeding(false);
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
          {/* Demo controls — only visible when DEMO_MODE=true on the backend */}
          {demoMode && (
            <>
              <Button
                size="small"
                variant="outlined"
                onClick={(e) => setSeedMenuAnchor(e.currentTarget)}
                disabled={seeding}
                startIcon={<AddCircleOutlinedIcon />}
                endIcon={<ArrowDropDownIcon />}
                sx={{ height: 30, color: "#a78bfa", borderColor: "#7c3aed55", "&:hover": { borderColor: "#a78bfa", bgcolor: "#7c3aed11" } }}
              >
                {seeding ? "Seeding…" : "Seed demo data"}
              </Button>
              <Menu
                anchorEl={seedMenuAnchor}
                open={Boolean(seedMenuAnchor)}
                onClose={() => setSeedMenuAnchor(null)}
                slotProps={{ paper: { sx: { bgcolor: "background.default", border: "1px solid rgba(255,255,255,0.1)", minWidth: 260 } } }}
              >
                {SCENARIOS.map((s) => (
                  <MenuItem key={s.id} onClick={() => seedScenario(s.id)} sx={{ py: 1 }}>
                    <ListItemIcon>
                      <ScienceOutlinedIcon sx={{ fontSize: 16, color: "#a78bfa" }} />
                    </ListItemIcon>
                    <ListItemText
                      primary={s.label}
                      secondary={s.description}
                      slotProps={{
                        primary: { sx: { fontSize: "0.8rem", color: "#a78bfa" } },
                        secondary: { sx: { fontSize: "0.68rem" } },
                      }}
                    />
                  </MenuItem>
                ))}
              </Menu>
              {hasDemo && (
                <Button
                  size="small"
                  variant="outlined"
                  onClick={clearDemoData}
                  disabled={clearing}
                  startIcon={<DeleteOutlineIcon />}
                  sx={{ height: 30, color: "#a78bfa", borderColor: "#7c3aed55", "&:hover": { borderColor: "#a78bfa", bgcolor: "#7c3aed11" } }}
                >
                  {clearing ? "Clearing…" : "Clear"}
                </Button>
              )}
            </>
          )}
          <Button size="small" variant="outlined" onClick={fetchGraph} disabled={loading} startIcon={<RefreshIcon />} sx={{ height: 30 }}>
            {loading ? "Loading…" : "Refresh"}
          </Button>
        </Stack>
      </Stack>

      {/* Demo mode banner — shown when demo mode is on, with or without seeded data */}
      {demoMode && (
        <Paper elevation={0} sx={{ p: 1.5, bgcolor: "#7c3aed11", border: "1px solid #7c3aed44", borderRadius: 2 }}>
          <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
            <ScienceOutlinedIcon sx={{ fontSize: 15, color: "#a78bfa", flexShrink: 0 }} />
            <Typography variant="caption" sx={{ color: "#a78bfa", flex: 1 }}>
              {hasDemo
                ? <>Demo data active: {demoDevCount > 0 ? `${demoDevCount} developer${demoDevCount !== 1 ? "s" : ""}` : ""}
                    {demoDevCount > 0 && demoModCount > 0 ? " · " : ""}
                    {demoModCount > 0 ? `${demoModCount} module${demoModCount !== 1 ? "s" : ""}` : ""} seeded.
                    Results include synthetic entries.</>
                : <>Demo mode enabled. No data seeded yet. Use <strong>Seed demo data</strong> to populate a scenario.</>
              }
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
            Graph is empty. Run the pipeline to populate per-module knowledge data.
          </Typography>
        </Paper>
      )}

      {/* Bus-factor drawer — opened when a developer name is clicked */}
      <BusfactorDrawer
        username={selectedDev}
        open={drawerOpen}
        onClose={() => setDrawerOpen(false)}
        apiUrl={apiUrl}
      />

      {hasGraph && (
        <>
          {/* Primary: module knowledge breakdown */}
          <Paper elevation={0} sx={{ p: 2.5 }}>
            <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 2 }}>
              Module Knowledge Breakdown
            </Typography>
            <ModuleBreakdown modules={data!.modules} findings={recentFindings} onSelectDev={openDevDrawer} demoMode={demoMode} />
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
