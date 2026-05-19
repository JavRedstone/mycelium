"use client";

import { useCallback, useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import RefreshOutlinedIcon from "@mui/icons-material/RefreshOutlined";
import ScienceOutlinedIcon from "@mui/icons-material/ScienceOutlined";

import {
  CartesianGrid,
  Label,
  ReferenceLine,
  Scatter,
  ScatterChart,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from "recharts";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── types ─────────────────────────────────────────────────────────────────────

type Developer = {
  username: string;
  name: string;
  last_seen?: string;
  active?: boolean;
  demo?: boolean;
  external?: boolean;
};

type Contribution = {
  developer_username: string;
  module_path: string;
  commit_count: number;
  lines_changed: number;
  expertise_score: number;
  last_contribution_at?: string;
  external?: boolean;
  demo?: boolean;
};

type Module = {
  path: string;
  bus_factor: number;
  owners: string[];
  language?: string;
  last_commit_at?: string;
  demo?: boolean;
  contributors: Contribution[];
};

// ── colour palette ────────────────────────────────────────────────────────────

const PALETTE = [
  "#1a73e8", "#34a853", "#ea4335", "#fbbc04",
  "#00bcd4", "#9c27b0", "#ff7043", "#26a69a",
  "#5c6bc0", "#ef5350",
];
function moduleColor(path: string, allPaths: string[]): string {
  return PALETTE[allPaths.indexOf(path) % PALETTE.length];
}

// ── helpers ───────────────────────────────────────────────────────────────────

function timeAgoFull(dateStr: string): string {
  const ms = Date.now() - new Date(dateStr).getTime();
  const days = Math.floor(ms / 86_400_000);
  if (days === 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days} days ago`;
  const months = Math.round(days / 30);
  return months === 1 ? "1 month ago" : `${months} months ago`;
}

function fmtShortDate(dateStr: string): string {
  return new Date(dateStr).toLocaleDateString([], { month: "short", day: "numeric" });
}

// ── recharts custom dot shapes ────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type DotProps = { cx?: number; cy?: number; payload?: any };

function ContribDot({ cx = 0, cy = 0, payload }: DotProps) {
  if (!payload) return null;
  const isPreFork: boolean = payload.isPreFork;
  return (
    <circle
      cx={cx}
      cy={cy}
      r={payload.r as number}
      fill={payload.color as string}
      opacity={isPreFork ? 0.3 : (payload.opacity as number)}
      stroke={isPreFork ? "none" : "rgba(0,0,0,0.35)"}
      strokeWidth={isPreFork ? 0 : 1.5}
    />
  );
}

function LastSeenMarker({ cx = 0, cy = 0, payload }: DotProps) {
  if (!payload) return null;
  const color = (payload.isInactive as boolean) ? "#ea4335" : "#34a853";
  return <rect x={cx - 1} y={cy - 14} width={2} height={28} fill={color} opacity={0.5} />;
}

// ── chart tooltip ─────────────────────────────────────────────────────────────

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function ScatterTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const p = payload[0]?.payload;
  if (!p) return null;

  if (p._isLastSeen) {
    const iso = new Date(p.x as number).toISOString();
    return (
      <Paper sx={{ px: 1.5, py: 1, bgcolor: "#21262d", border: "1px solid rgba(255,255,255,0.1)" }}>
        <Typography variant="caption" sx={{ fontWeight: 600, color: p.isInactive ? "#ea4335" : "#34a853", display: "block" }}>
          {p.devName as string}
        </Typography>
        <Typography variant="caption" color="text.secondary">
          Last seen: {fmtShortDate(iso)} ({timeAgoFull(iso)}) · {p.isInactive ? "inactive" : "active"}
        </Typography>
      </Paper>
    );
  }

  const iso = new Date(p.x as number).toISOString();
  return (
    <Paper sx={{ px: 1.5, py: 1, bgcolor: "#21262d", border: "1px solid rgba(255,255,255,0.1)" }}>
      <Typography variant="caption" sx={{ fontWeight: 600, display: "block" }}>{p.devName as string}</Typography>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>{p.module as string}/</Typography>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
        {p.commitCount as number} commits · {Math.round((p.expertise as number) * 100)}% expertise
      </Typography>
      <Typography variant="caption" color="text.disabled" sx={{ display: "block" }}>
        {p.isPreFork ? "upstream · " : ""}{fmtShortDate(iso)} ({timeAgoFull(iso)})
      </Typography>
    </Paper>
  );
}

// ── module status row ─────────────────────────────────────────────────────────

function ModuleStatusRow({ mod, modulePaths }: { mod: Module; modulePaths: string[] }) {
  const color = moduleColor(mod.path, modulePaths);
  const internal = mod.contributors.filter((c) => !c.external);
  const primary = internal.length
    ? internal.reduce((a, b) => (a.expertise_score > b.expertise_score ? a : b))
    : null;

  const lastTouched = internal
    .map((c) => c.last_contribution_at ? new Date(c.last_contribution_at).getTime() : 0)
    .reduce((a, b) => Math.max(a, b), 0);
  const lastTouchedStr = lastTouched ? new Date(lastTouched).toISOString() : undefined;
  const staleDays = lastTouched ? (Date.now() - lastTouched) / 86_400_000 : Infinity;
  const isStale = staleDays > 60;

  return (
    <Stack direction="row" spacing={1.5} sx={{ alignItems: "center", py: 0.75 }}>
      <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: color, flexShrink: 0 }} />
      <Typography variant="caption" sx={{ fontFamily: "monospace", fontWeight: 600, width: 110, flexShrink: 0, color: isStale ? "#ea4335" : "text.primary" }}>
        {mod.path}/
      </Typography>
      <Chip
        label={`bus ${mod.bus_factor}`}
        size="small"
        sx={{
          height: 16, fontSize: "0.6rem",
          bgcolor: mod.bus_factor <= 0 ? "rgba(234,67,53,0.15)" : mod.bus_factor === 1 ? "rgba(251,188,4,0.12)" : "rgba(52,168,83,0.1)",
          color: mod.bus_factor <= 0 ? "#ea4335" : mod.bus_factor === 1 ? "#fbbc04" : "#34a853",
          border: "none",
          "& .MuiChip-label": { px: 0.75 },
        }}
      />
      <Typography variant="caption" color="text.secondary" sx={{ flex: 1 }}>
        {internal.length} contributor{internal.length !== 1 ? "s" : ""}
        {primary ? ` · led by ${primary.developer_username}` : ""}
      </Typography>
      <Typography variant="caption" color={isStale ? "#ea4335" : "text.disabled"} sx={{ fontFamily: "monospace", fontSize: "0.68rem", flexShrink: 0 }}>
        {lastTouchedStr ? timeAgoFull(lastTouchedStr) : "—"}
      </Typography>
      {mod.demo && <ScienceOutlinedIcon sx={{ fontSize: 11, color: "#a78bfa", flexShrink: 0 }} />}
    </Stack>
  );
}

// ── main component ────────────────────────────────────────────────────────────

export default function RepoHistory() {
  const [allDevs, setAllDevs] = useState<Developer[]>([]);
  const [modules, setModules] = useState<Module[]>([]);
  const [forkDateInfo, setForkDateInfo] = useState<{ effective?: string | null; override?: string | null }>({});
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [devRes, graphRes, forkRes] = await Promise.all([
        fetch(`${API}/developers`),
        fetch(`${API}/graph`),
        fetch(`${API}/settings/fork-date`),
      ]);
      const devData = await devRes.json();
      const graphData = await graphRes.json();
      const forkData = forkRes.ok ? await forkRes.json() : {};
      setAllDevs(devData.developers ?? []);
      setModules(graphData.modules ?? []);
      setForkDateInfo(forkData);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}><CircularProgress size={28} /></Box>;
  }

  // Split into internal and upstream authors
  const internalDevs = allDevs.filter((d) => !d.external);
  const upstreamAuthors = allDevs.filter((d) => d.external);

  if (internalDevs.length === 0 && upstreamAuthors.length === 0) {
    return (
      <Paper variant="outlined" sx={{ p: 4, textAlign: "center", borderColor: "rgba(255,255,255,0.08)" }}>
        <Typography variant="body2" color="text.disabled">
          No contributors in the knowledge graph yet. Run the pipeline or seed demo data.
        </Typography>
      </Paper>
    );
  }

  // Determine time range from all timestamps
  const allTimestamps: number[] = [];
  for (const dev of allDevs) {
    if (dev.last_seen) allTimestamps.push(new Date(dev.last_seen).getTime());
  }
  for (const mod of modules) {
    for (const c of mod.contributors) {
      if (c.last_contribution_at) allTimestamps.push(new Date(c.last_contribution_at).getTime());
    }
  }
  const now = Date.now();
  const oldest = allTimestamps.length ? Math.min(...allTimestamps) : now - 365 * 86_400_000;
  const rangeMs = Math.max(now - oldest + 14 * 86_400_000, 180 * 86_400_000);
  const startMs = now - rangeMs;

  const modulePaths = [...new Set(modules.map((m) => m.path))].sort();

  // Only show developers who have at least one contribution in the module data
  const contributingUsernames = new Set(
    modules.flatMap((m) => m.contributors.map((c) => c.developer_username))
  );

  const sortedInternal = [...internalDevs]
    .filter((d) => contributingUsernames.has(d.username))
    .sort((a, b) => {
      const aMs = a.last_seen ? new Date(a.last_seen).getTime() : 0;
      const bMs = b.last_seen ? new Date(b.last_seen).getTime() : 0;
      return bMs - aMs;
    });
  const sortedUpstream = [...upstreamAuthors]
    .filter((d) => contributingUsernames.has(d.username))
    .sort((a, b) => {
      const aMs = a.last_seen ? new Date(a.last_seen).getTime() : 0;
      const bMs = b.last_seen ? new Date(b.last_seen).getTime() : 0;
      return bMs - aMs;
    });

  const hasUpstream = sortedUpstream.length > 0;

  // Y axis layout: internal rows 0..N-1, separator gap at N, upstream rows N+1..N+U
  const N = sortedInternal.length;
  const U = sortedUpstream.length;
  const separatorY = N; // gap row — no data, just a reference line

  function rowIndex(dev: Developer): number {
    const ii = sortedInternal.findIndex((d) => d.username === dev.username);
    if (ii >= 0) return ii;
    const ui = sortedUpstream.findIndex((d) => d.username === dev.username);
    if (ui >= 0) return N + 1 + ui;
    return -1;
  }

  const yTicks = [
    ...sortedInternal.map((_, i) => i),
    ...(hasUpstream ? sortedUpstream.map((_, i) => N + 1 + i) : []),
  ];

  function tickLabel(i: number): string {
    if (i < N) return sortedInternal[i]?.name ?? "";
    return sortedUpstream[i - N - 1]?.name ?? "";
  }

  const totalRows = N + (hasUpstream ? U + 1 : 0);
  const yDomain = [-0.5, totalRows - 0.5];

  // Fork / repo-start reference line
  const repoStartMs = forkDateInfo.effective ? new Date(forkDateInfo.effective).getTime() : null;
  const repoStartLabel = forkDateInfo.override ? "fork date (demo)" : "repo start";

  // Build scatter series data per module
  const moduleSeriesData: Record<string, object[]> = Object.fromEntries(modulePaths.map((p) => [p, []]));
  // Last-seen markers
  const lastSeenData: object[] = [];

  for (const mod of modules) {
    for (const c of mod.contributors) {
      if (!c.last_contribution_at) continue;
      const x = new Date(c.last_contribution_at).getTime();

      // Find the developer to get Y position
      const dev = allDevs.find((d) => d.username === c.developer_username);
      if (!dev) continue;

      const yPos = rowIndex(dev);
      if (yPos < 0) continue;

      const isPreFork = repoStartMs != null ? x < repoStartMs : false;

      // Post-fork external: skip (upstream authors shouldn't have post-fork contributions)
      if (!isPreFork && dev.external) continue;

      const inactiveDays = dev.last_seen ? (Date.now() - new Date(dev.last_seen).getTime()) / 86_400_000 : 0;

      (moduleSeriesData[c.module_path] ??= []).push({
        x,
        y: yPos,
        r: Math.max(4, Math.min(9, Math.round(c.expertise_score * 7) + 4)),
        color: moduleColor(c.module_path, modulePaths),
        opacity: inactiveDays > 60 ? 0.4 : 0.85,
        isPreFork,
        module: c.module_path,
        devName: dev.name,
        expertise: c.expertise_score,
        commitCount: c.commit_count,
      });
    }
  }

  // Last-seen markers for internal devs only (active/inactive line)
  for (const [i, dev] of sortedInternal.entries()) {
    if (!dev.last_seen) continue;
    const ms = new Date(dev.last_seen).getTime();
    lastSeenData.push({
      x: ms,
      y: i,
      isInactive: (Date.now() - ms) / 86_400_000 > 60,
      devName: dev.name,
      _isLastSeen: true,
    });
  }

  const Y_PANEL = 160;
  const MARGIN_TOP = 8;
  const MARGIN_BOTTOM = 8;
  const chartHeight = Math.max(160, totalRows * 36 + 40);
  const chartDataHeight = chartHeight - MARGIN_TOP - MARGIN_BOTTOM;
  const monthCount = Math.ceil(rangeMs / (30 * 86_400_000));
  const dataWidth = Math.max(700, monthCount * 90);

  function labelPixelY(tick: number): number {
    return MARGIN_TOP + (tick + 0.5) / totalRows * chartDataHeight;
  }

  // Sort modules most recently active first for the table
  const sortedModules = [...modules].sort((a, b) => {
    const latest = (m: Module) =>
      Math.max(...m.contributors.filter((c) => !c.external).map((c) => c.last_contribution_at ? new Date(c.last_contribution_at).getTime() : 0), 0);
    return latest(b) - latest(a);
  });

  return (
    <Stack spacing={3}>
      {/* Legend */}
      <Stack direction="row" spacing={2} sx={{ flexWrap: "wrap", alignItems: "center" }} useFlexGap>
        {modulePaths.map((path) => (
          <Stack key={path} direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
            <Box sx={{ width: 10, height: 10, borderRadius: "50%", bgcolor: moduleColor(path, modulePaths), flexShrink: 0 }} />
            <Typography variant="caption" color="text.secondary" sx={{ fontFamily: "monospace", fontSize: "0.72rem" }}>
              {path}/
            </Typography>
          </Stack>
        ))}
        <Stack direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
          <Box sx={{ width: 2, height: 12, bgcolor: "#34a853", opacity: 0.6, flexShrink: 0 }} />
          <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.68rem" }}>last seen (active)</Typography>
        </Stack>
        <Stack direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
          <Box sx={{ width: 2, height: 12, bgcolor: "#ea4335", opacity: 0.6, flexShrink: 0 }} />
          <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.68rem" }}>last seen (inactive)</Typography>
        </Stack>
        <Box sx={{ flex: 1 }} />
        <IconButton size="small" onClick={load} sx={{ color: "text.disabled" }}>
          <RefreshOutlinedIcon sx={{ fontSize: 16 }} />
        </IconButton>
      </Stack>

      {/* Contributor activity — sticky Y axis + scrollable chart */}
      <Paper variant="outlined" sx={{ borderColor: "rgba(255,255,255,0.08)", borderRadius: 2, overflow: "hidden" }}>
        <Box sx={{ px: 2.5, py: 1.5, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
          <Typography variant="subtitle2" color="text.secondary">Contributor activity</Typography>
        </Box>

        <Box sx={{ display: "flex", overflow: "hidden" }}>
          {/* ── Sticky Y axis panel ── */}
          <Box
            sx={{
              width: Y_PANEL,
              flexShrink: 0,
              position: "relative",
              height: chartHeight,
              bgcolor: "background.paper",
              borderRight: "1px solid rgba(255,255,255,0.06)",
              zIndex: 2,
            }}
          >
            {yTicks.map((tick) => {
              const isUpstream = hasUpstream && tick >= N + 1;
              return (
                <Typography
                  key={tick}
                  sx={{
                    position: "absolute",
                    top: labelPixelY(tick),
                    right: 8,
                    transform: "translateY(-50%)",
                    fontSize: "0.68rem",
                    lineHeight: 1,
                    color: isUpstream ? "#8b949e" : "#c9d1d9",
                    fontStyle: isUpstream ? "italic" : "normal",
                    whiteSpace: "nowrap",
                    maxWidth: Y_PANEL - 12,
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                    userSelect: "none",
                  }}
                >
                  {tickLabel(tick)}
                </Typography>
              );
            })}

            {/* Separator + "upstream authors" micro-label */}
            {hasUpstream && (() => {
              const sepY = labelPixelY(N - 0.5 + 0.5); // midpoint of gap row
              return (
                <>
                  <Box sx={{ position: "absolute", top: sepY, left: 0, right: 0, borderTop: "1px dashed rgba(255,255,255,0.1)" }} />
                  <Typography sx={{ position: "absolute", top: sepY + 3, right: 8, fontSize: "0.58rem", color: "rgba(255,255,255,0.25)", fontStyle: "italic", fontFamily: "monospace", lineHeight: 1 }}>
                    upstream
                  </Typography>
                </>
              );
            })()}
          </Box>

          {/* ── Scrollable data area ── */}
          <Box sx={{ overflowX: "auto", flex: 1 }}>
            <Box sx={{ width: dataWidth }}>
              <ScatterChart width={dataWidth} height={chartHeight} margin={{ top: MARGIN_TOP, right: 32, bottom: MARGIN_BOTTOM, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis
                  dataKey="x"
                  type="number"
                  scale="time"
                  domain={[startMs, now]}
                  tickFormatter={(ms: number) =>
                    new Date(ms).toLocaleDateString([], { month: "short", year: "2-digit" })
                  }
                  tick={{ fill: "#8b949e", fontSize: 11 }}
                  axisLine={{ stroke: "rgba(255,255,255,0.08)" }}
                  tickLine={false}
                  tickCount={6}
                />
                {/* Y axis hidden — labels rendered in sticky HTML panel */}
                <YAxis
                  dataKey="y"
                  type="number"
                  domain={yDomain}
                  ticks={yTicks}
                  reversed
                  width={0}
                  tick={false}
                  axisLine={false}
                  tickLine={false}
                />
                <ChartTooltip content={<ScatterTooltip />} cursor={false} />

                {/* Fork / repo-start reference line */}
                {repoStartMs != null && repoStartMs >= startMs && (
                  <ReferenceLine
                    x={repoStartMs}
                    stroke="rgba(255,255,255,0.5)"
                    strokeWidth={1.5}
                    strokeDasharray="6 3"
                  >
                    <Label
                      value={repoStartLabel}
                      position="insideTopRight"
                      style={{ fill: "rgba(255,255,255,0.45)", fontSize: 10, fontFamily: "monospace" }}
                      offset={6}
                    />
                  </ReferenceLine>
                )}

                {/* Separator between internal and upstream rows */}
                {hasUpstream && (
                  <ReferenceLine
                    y={separatorY + 0.5}
                    stroke="rgba(255,255,255,0.08)"
                    strokeDasharray="4 4"
                  />
                )}

                {/* Last-seen markers */}
                <Scatter
                  data={lastSeenData}
                  shape={(props: DotProps) => <LastSeenMarker {...props} />}
                  isAnimationActive={false}
                  legendType="none"
                />

                {/* One series per module */}
                {modulePaths.map((path) => (
                  <Scatter
                    key={path}
                    name={path}
                    data={moduleSeriesData[path] ?? []}
                    shape={(props: DotProps) => <ContribDot {...props} />}
                    isAnimationActive={false}
                    legendType="none"
                  />
                ))}
              </ScatterChart>
            </Box>
          </Box>
        </Box>
      </Paper>

      {/* Module last-activity table */}
      <Paper variant="outlined" sx={{ borderColor: "rgba(255,255,255,0.08)", borderRadius: 2, overflow: "hidden" }}>
        <Box sx={{ px: 2.5, py: 1.5, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
          <Typography variant="subtitle2" color="text.secondary">Module last activity</Typography>
        </Box>
        <Box sx={{ px: 2.5, py: 1.5 }}>
          <Stack divider={<Divider sx={{ borderColor: "rgba(255,255,255,0.04)" }} />}>
            {sortedModules.map((mod) => (
              <ModuleStatusRow key={mod.path} mod={mod} modulePaths={modulePaths} />
            ))}
          </Stack>
        </Box>
      </Paper>
    </Stack>
  );
}
