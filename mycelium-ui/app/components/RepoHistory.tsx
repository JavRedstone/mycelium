"use client";

import { useCallback, useEffect, useRef, useState } from "react";
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
import { filterModules } from "../lib/graphFilters";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── types ─────────────────────────────────────────────────────────────────────

type Developer = {
  username: string;
  name: string;
  first_seen?: string;
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

type ContribHistoryRecord = {
  developer_username: string;
  module_path: string;
  year_month: string;
  commit_count: number;
  external: boolean;
  demo?: boolean;
};

type ActivityBar = {
  username: string;
  devName: string;
  yRow: number;
  startMs: number;
  endMs: number;
  monthCount: number;
  totalCommits: number;
  isUpstream: boolean;
  isPreFork: boolean;
  isInactive: boolean;
};

type Tooltip = {
  clientX: number;
  clientY: number;
  devName: string;
  range: string;
  commits: number;
  months: number;
  isUpstream: boolean;
  isPreFork: boolean;
} | null;

// ── palette (fallback dots) ───────────────────────────────────────────────────

const PALETTE = [
  "#1a73e8", "#34a853", "#ea4335", "#fbbc04",
  "#00bcd4", "#9c27b0", "#ff7043", "#26a69a",
  "#5c6bc0", "#ef5350",
];
function moduleColor(path: string, allPaths: string[]): string {
  return PALETTE[allPaths.indexOf(path) % PALETTE.length];
}

// ── helpers ───────────────────────────────────────────────────────────────────

function timeAgoFull(ms: number): string {
  const days = Math.floor((Date.now() - ms) / 86_400_000);
  if (days === 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days}d ago`;
  const months = Math.round(days / 30);
  return months === 1 ? "1mo ago" : `${months}mo ago`;
}

/** ISO date string "YYYY-MM-DD" from a millisecond timestamp — used for line labels. */
function fmtDateIso(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10);
}

function isConsecutiveMonths(a: string, b: string): boolean {
  const [ay, am] = a.split("-").map(Number);
  const [by, bm] = b.split("-").map(Number);
  return (by - ay) * 12 + (bm - am) === 1;
}

// Returns the exact first millisecond of the given month.
function monthStartMs(yearMonth: string): number {
  return new Date(yearMonth + "-01T00:00:00.000").getTime();
}

// Returns the first millisecond of the month AFTER the given one (exclusive end),
// so a bar drawn [start, end) covers the full calendar month exactly.
function monthEndMs(yearMonth: string): number {
  const [y, m] = yearMonth.split("-").map(Number);
  const nextMonth = m === 12 ? 1 : m + 1;
  const nextYear  = m === 12 ? y + 1 : y;
  return new Date(`${nextYear}-${String(nextMonth).padStart(2, "0")}-01T00:00:00.000`).getTime();
}

function computeActivityBars(
  monthlyByUser: Map<string, Map<string, number>>,
  allDevs: Developer[],
  rowIndexFn: (username: string) => number,
  repoStartMs: number | null,
): ActivityBar[] {
  const devByUsername = new Map(allDevs.map((d) => [d.username, d]));
  const bars: ActivityBar[] = [];

  for (const [username, monthMap] of monthlyByUser) {
    const dev = devByUsername.get(username);
    if (!dev) continue;
    const yRow = rowIndexFn(username);
    if (yRow < 0) continue;

    const sortedMonths = [...monthMap.keys()].sort();
    if (!sortedMonths.length) continue;

    const INACTIVE_DAYS = 60;
    const isInactive = dev.last_seen
      ? (Date.now() - new Date(dev.last_seen).getTime()) / 86_400_000 > INACTIVE_DAYS
      : true;

    // Collect this developer's bars separately so we can snap the final one.
    const devBars: ActivityBar[] = [];

    function emitBar(months: string[]) {
      const startMs = monthStartMs(months[0]);
      const endMs   = monthEndMs(months[months.length - 1]);
      const isPreFork = repoStartMs != null ? startMs < repoStartMs : false;
      if (!isPreFork && dev!.external) return; // upstream only visible pre-fork
      devBars.push({
        username,
        devName: dev!.name,
        yRow,
        startMs,
        endMs,
        monthCount: months.length,
        totalCommits: months.reduce((s, m) => s + (monthMap.get(m) ?? 0), 0),
        isUpstream: !!dev!.external,
        isPreFork,
        isInactive,
      });
    }

    let run: string[] = [sortedMonths[0]];
    for (let i = 1; i < sortedMonths.length; i++) {
      if (isConsecutiveMonths(sortedMonths[i - 1], sortedMonths[i])) {
        run.push(sortedMonths[i]);
      } else {
        emitBar(run);
        run = [sortedMonths[i]];
      }
    }
    emitBar(run);

    // Snap the left edge of the earliest bar to the developer's exact first_seen
    // date, mirroring the right-edge snap to last_seen.
    if (dev.first_seen && devBars.length > 0) {
      const firstSeenMs = new Date(dev.first_seen).getTime();
      const earliestBar = devBars.reduce((a, b) => (a.startMs <= b.startMs ? a : b));
      if (firstSeenMs > earliestBar.startMs && firstSeenMs <= earliestBar.endMs) {
        earliestBar.startMs = firstSeenMs;
      }
    }

    // For internal devs: any bar that straddles the fork date gets its left edge
    // snapped to the fork date (contributions become "internal" at that moment).
    // Runs after the first_seen snap so fork-date always wins over an earlier exact date.
    if (repoStartMs != null && !dev!.external) {
      for (const bar of devBars) {
        if (bar.startMs < repoStartMs && bar.endMs > repoStartMs) {
          bar.startMs  = repoStartMs;
          bar.isPreFork = false;
        }
      }
    }

    // Snap the right edge of the most recent bar to the developer's exact last_seen
    // date so it aligns with the vertical marker on the chart.
    if (devBars.length > 0 && dev.last_seen) {
      const lastSeenMs = new Date(dev.last_seen).getTime();
      const latestBar = devBars.reduce((a, b) => (a.endMs >= b.endMs ? a : b));
      // Only snap if last_seen falls within or at the bar's range.
      if (lastSeenMs >= latestBar.startMs && lastSeenMs <= latestBar.endMs) {
        latestBar.endMs = lastSeenMs;
      }
    }

    bars.push(...devBars);
  }
  return bars;
}

// ── module status row ─────────────────────────────────────────────────────────

function ModuleStatusRow({ mod, modulePaths }: { mod: Module; modulePaths: string[] }) {
  const color = moduleColor(mod.path, modulePaths);
  const internal = mod.contributors.filter((c) => !c.external);
  const primary = internal.length
    ? internal.reduce((a, b) => (a.expertise_score > b.expertise_score ? a : b))
    : null;
  const lastTouched = internal
    .map((c) => (c.last_contribution_at ? new Date(c.last_contribution_at).getTime() : 0))
    .reduce((a, b) => Math.max(a, b), 0);
  const staleDays = lastTouched ? (Date.now() - lastTouched) / 86_400_000 : Infinity;
  const isStale = staleDays > 60;
  return (
    <Stack direction="row" spacing={1.5} sx={{ alignItems: "center", py: 0.75 }}>
      <Box sx={{ width: 8, height: 8, borderRadius: "50%", bgcolor: color, flexShrink: 0 }} />
      <Typography variant="caption" sx={{ fontFamily: "monospace", fontWeight: 600, width: 110, flexShrink: 0, color: isStale ? "#ea4335" : "text.primary" }}>
        {mod.path}/
      </Typography>
      <Chip label={`bus ${mod.bus_factor}`} size="small" sx={{
        height: 16, fontSize: "0.6rem", border: "none",
        bgcolor: mod.bus_factor <= 0 ? "rgba(234,67,53,0.15)" : mod.bus_factor === 1 ? "rgba(251,188,4,0.12)" : "rgba(52,168,83,0.1)",
        color: mod.bus_factor <= 0 ? "#ea4335" : mod.bus_factor === 1 ? "#fbbc04" : "#34a853",
        "& .MuiChip-label": { px: 0.75 },
      }} />
      <Typography variant="caption" color="text.secondary" sx={{ flex: 1 }}>
        {internal.length} contributor{internal.length !== 1 ? "s" : ""}
        {primary ? ` · led by ${primary.developer_username}` : ""}
      </Typography>
      <Typography variant="caption" color={isStale ? "#ea4335" : "text.disabled"} sx={{ fontFamily: "monospace", fontSize: "0.68rem", flexShrink: 0 }}>
        {lastTouched ? timeAgoFull(lastTouched) : "-"}
      </Typography>
      {mod.demo && <ScienceOutlinedIcon sx={{ fontSize: 11, color: "#a78bfa", flexShrink: 0 }} />}
    </Stack>
  );
}

// ── main component ────────────────────────────────────────────────────────────

export default function RepoHistory() {
  const [allDevs, setAllDevs]       = useState<Developer[]>([]);
  const [modules, setModules]       = useState<Module[]>([]);
  const [forkDateInfo, setForkDateInfo] = useState<{ effective?: string | null; override?: string | null }>({});
  const [contribHistory, setContribHistory] = useState<ContribHistoryRecord[]>([]);
  const [loading, setLoading]       = useState(true);
  const [tooltip, setTooltip]       = useState<Tooltip>(null);
  const [hoveredBar, setHoveredBar] = useState<number | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [devRes, graphRes, forkRes, histRes] = await Promise.all([
        fetch(`${API}/developers`),
        fetch(`${API}/graph`),
        fetch(`${API}/settings/fork-date`),
        fetch(`${API}/graph/contribution-history`),
      ]);
      const [devData, graphData, forkData, histData] = await Promise.all([
        devRes.json(), graphRes.json(),
        forkRes.ok ? forkRes.json() : {},
        histRes.ok ? histRes.json() : [],
      ]);
      setAllDevs(devData.developers ?? []);
      setModules(filterModules(graphData.modules ?? []));
      setForkDateInfo(forkData);
      setContribHistory(Array.isArray(histData) ? histData : []);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Scroll timeline to the right (most recent activity) after data loads
  useEffect(() => {
    if (!loading && scrollRef.current) {
      scrollRef.current.scrollLeft = scrollRef.current.scrollWidth;
    }
  }, [loading]);

  if (loading) {
    return <Box sx={{ display: "flex", justifyContent: "center", py: 8 }}><CircularProgress size={28} /></Box>;
  }

  const internalDevs  = allDevs.filter((d) => !d.external);
  const upstreamAuthors = allDevs.filter((d) => d.external);

  if (!internalDevs.length && !upstreamAuthors.length) {
    return (
      <Paper variant="outlined" sx={{ p: 4, textAlign: "center", borderColor: "rgba(255,255,255,0.08)" }}>
        <Typography variant="body2" color="text.disabled">
          No contributors in the knowledge graph yet. Run the pipeline or seed demo data.
        </Typography>
      </Paper>
    );
  }

  const now = Date.now();
  const modulePaths = [...new Set(modules.map((m) => m.path))].sort();

  const contributingUsernames = new Set([
    ...modules.flatMap((m) => m.contributors.map((c) => c.developer_username)),
    ...contribHistory.map((r) => r.developer_username),
  ]);

  // Time range — wide enough to cover all monthly history
  const allTimestamps: number[] = [now - 180 * 86_400_000]; // minimum 6 months
  for (const dev of allDevs)
    if (dev.last_seen) allTimestamps.push(new Date(dev.last_seen).getTime());
  for (const mod of modules)
    for (const c of mod.contributors)
      if (c.last_contribution_at) allTimestamps.push(new Date(c.last_contribution_at).getTime());
  for (const r of contribHistory)
    allTimestamps.push(new Date(r.year_month + "-15").getTime());

  const oldest  = Math.min(...allTimestamps);
  const rangeMs = Math.max(now - oldest + 14 * 86_400_000, 180 * 86_400_000);
  const startMs = now - rangeMs;

  const sortedInternal = [...internalDevs]
    .filter((d) => contributingUsernames.has(d.username))
    .sort((a, b) => (new Date(b.last_seen ?? 0).getTime()) - (new Date(a.last_seen ?? 0).getTime()));

  const sortedUpstream = [...upstreamAuthors]
    .filter((d) => contributingUsernames.has(d.username))
    .sort((a, b) => (new Date(b.last_seen ?? 0).getTime()) - (new Date(a.last_seen ?? 0).getTime()))
    .slice(0, 15);

  const hasUpstream = sortedUpstream.length > 0;
  const N = sortedInternal.length;
  const U = sortedUpstream.length;
  const totalRows = N + (hasUpstream ? U + 1 : 0);

  function rowIndexByUsername(username: string): number {
    const ii = sortedInternal.findIndex((d) => d.username === username);
    if (ii >= 0) return ii;
    const ui = sortedUpstream.findIndex((d) => d.username === username);
    return ui >= 0 ? N + 1 + ui : -1;
  }

  const yTicks = [
    ...sortedInternal.map((_, i) => i),
    ...(hasUpstream ? sortedUpstream.map((_, i) => N + 1 + i) : []),
  ];

  const repoStartMs    = forkDateInfo.effective ? new Date(forkDateInfo.effective).getTime() : null;
  const repoStartLabel = forkDateInfo.override ? "fork date (demo)" : "repo start";

  // ── Monthly activity bars ─────────────────────────────────────────────────

  const hasMonthlyData = contribHistory.length > 0;

  const monthlyByUser = new Map<string, Map<string, number>>();
  for (const r of contribHistory) {
    const m = monthlyByUser.get(r.developer_username) ?? new Map<string, number>();
    m.set(r.year_month, (m.get(r.year_month) ?? 0) + r.commit_count);
    monthlyByUser.set(r.developer_username, m);
  }

  const activityBars = hasMonthlyData
    ? computeActivityBars(monthlyByUser, allDevs, rowIndexByUsername, repoStartMs)
    : [];

  // Fallback: per-module dots when no monthly history available
  type FallbackDot = { cx: number; cy: number; r: number; fill: string; opacity: number; stroke: string; strokeWidth: number };
  const fallbackDots: FallbackDot[] = [];

  // ── SVG layout ────────────────────────────────────────────────────────────

  const Y_PANEL        = 160;
  const MARGIN_TOP     = 30;   // extra headroom for two-line labels above global vertical lines
  const MARGIN_BOTTOM  = 4;
  const X_AXIS_H       = 28;
  const ROW_HEIGHT     = 36;
  const BAR_H          = 16;
  const chartHeight    = Math.max(160, totalRows * ROW_HEIGHT + MARGIN_TOP + MARGIN_BOTTOM + X_AXIS_H);
  const chartDataH     = chartHeight - MARGIN_TOP - MARGIN_BOTTOM - X_AXIS_H;
  const monthCount     = Math.ceil(rangeMs / (30 * 86_400_000));
  const dataWidth      = Math.max(700, monthCount * 90);
  const PLOT_W         = dataWidth - 32;

  function rowCY(tick: number): number {
    return MARGIN_TOP + (tick + 0.5) / totalRows * chartDataH;
  }

  function msToX(ms: number): number {
    return Math.max(0, Math.min(PLOT_W, ((ms - startMs) / rangeMs) * PLOT_W));
  }

  // X axis tick marks — one per N months depending on zoom
  const tickEvery = Math.max(1, Math.round(monthCount / Math.floor(dataWidth / 70)));
  const xTicks: { ms: number; label: string }[] = [];
  {
    const d = new Date(startMs);
    d.setDate(1); d.setHours(0, 0, 0, 0);
    while (d.getTime() <= now + 30 * 86_400_000) {
      xTicks.push({ ms: d.getTime(), label: d.toLocaleDateString([], { month: "short", year: "2-digit" }) });
      d.setMonth(d.getMonth() + tickEvery);
    }
  }

  const gridY1    = MARGIN_TOP;
  const gridY2    = chartHeight - X_AXIS_H - MARGIN_BOTTOM;
  const labelY    = chartHeight - 6;

  // Fallback dots (used only if no monthly data)
  if (!hasMonthlyData) {
    for (const mod of modules) {
      for (const c of mod.contributors) {
        if (!c.last_contribution_at) continue;
        const dev = allDevs.find((d) => d.username === c.developer_username);
        if (!dev) continue;
        const yi = rowIndexByUsername(dev.username);
        if (yi < 0) continue;
        const xMs = new Date(c.last_contribution_at).getTime();
        const isPreFork = repoStartMs != null ? xMs < repoStartMs : false;
        if (!isPreFork && dev.external) continue;
        const inactiveDays = dev.last_seen ? (Date.now() - new Date(dev.last_seen).getTime()) / 86_400_000 : 0;
        fallbackDots.push({
          cx: msToX(xMs),
          cy: rowCY(yi),
          r: Math.max(4, Math.min(9, Math.round(c.expertise_score * 7) + 4)),
          fill: moduleColor(mod.path, modulePaths),
          opacity: isPreFork ? 0.3 : (inactiveDays > 60 ? 0.4 : 0.85),
          stroke: isPreFork ? "none" : "rgba(0,0,0,0.35)",
          strokeWidth: isPreFork ? 0 : 1.5,
        });
      }
    }
  }

  // Last-seen markers (vertical line + annotation = when contributor was last active)
  const lastSeenMarkers = sortedInternal
    .map((dev, i) => ({ dev, i }))
    .filter(({ dev }) => !!dev.last_seen)
    .map(({ dev, i }) => {
      const ms = new Date(dev.last_seen!).getTime();
      const daysAgo = (Date.now() - ms) / 86_400_000;
      const isInactive = daysAgo > 60;
      // Build a short annotation that goes to the right of the marker line.
      const timeLabel = timeAgoFull(ms);
      const annotation = isInactive
        ? `${timeLabel} · no recent commits`
        : timeLabel;
      return { x: msToX(ms), cy: rowCY(i), isInactive, annotation };
    });

  // Module table
  const sortedModules = [...modules].sort((a, b) => {
    const latest = (m: Module) =>
      Math.max(...m.contributors.filter((c) => !c.external).map((c) => c.last_contribution_at ? new Date(c.last_contribution_at).getTime() : 0), 0);
    return latest(b) - latest(a);
  });

  return (
    <Stack spacing={3}>
      {/* ── Legend ── */}
      <Stack direction="row" spacing={2} sx={{ flexWrap: "wrap", alignItems: "center" }} useFlexGap>
        {hasMonthlyData ? (
          <>
            <Stack direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
              <Box sx={{ width: 20, height: 10, borderRadius: "2px", bgcolor: "#4ade80", opacity: 0.88, flexShrink: 0 }} />
              <Typography variant="caption" color="text.secondary" sx={{ fontSize: "0.72rem" }}>active</Typography>
            </Stack>
            <Stack direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
              <Box sx={{ width: 20, height: 10, borderRadius: "2px", bgcolor: "#f87171", opacity: 0.88, flexShrink: 0 }} />
              <Typography variant="caption" color="text.secondary" sx={{ fontSize: "0.72rem" }}>no recent commits</Typography>
            </Stack>
            <Stack direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
              <Box sx={{ width: 20, height: 10, borderRadius: "2px", bgcolor: "#94a3b8", opacity: 0.5, flexShrink: 0 }} />
              <Typography variant="caption" color="text.secondary" sx={{ fontSize: "0.72rem" }}>pre-fork</Typography>
            </Stack>
            <Stack direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
              <Box sx={{ width: 2, height: 12, bgcolor: "#f87171", opacity: 0.35, flexShrink: 0 }} />
              <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.68rem" }}>60d cutoff</Typography>
            </Stack>
            <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.68rem" }}>· bars span contiguous active months</Typography>
          </>
        ) : (
          modulePaths.map((path) => (
            <Stack key={path} direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
              <Box sx={{ width: 10, height: 10, borderRadius: "50%", bgcolor: moduleColor(path, modulePaths), flexShrink: 0 }} />
              <Typography variant="caption" color="text.secondary" sx={{ fontFamily: "monospace", fontSize: "0.72rem" }}>{path}/</Typography>
            </Stack>
          ))
        )}
        <Stack direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
          <Box sx={{ width: 2, height: 12, bgcolor: "#34a853", opacity: 0.6, flexShrink: 0 }} />
          <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.68rem" }}>last seen</Typography>
        </Stack>
        <Box sx={{ flex: 1 }} />
        <IconButton size="small" onClick={load} sx={{ color: "text.disabled" }}>
          <RefreshOutlinedIcon sx={{ fontSize: 16 }} />
        </IconButton>
      </Stack>

      {/* ── Timeline chart ── */}
      <Paper variant="outlined" sx={{ borderColor: "rgba(255,255,255,0.08)", borderRadius: 2, overflow: "hidden" }}>
        <Box sx={{ px: 2.5, py: 1.5, borderBottom: "1px solid rgba(255,255,255,0.06)" }}>
          <Typography variant="subtitle2" color="text.secondary">Contributor activity timeline</Typography>
        </Box>

        <Box sx={{ display: "flex", overflow: "hidden" }}>
          {/* Sticky Y axis */}
          <Box sx={{ width: Y_PANEL, flexShrink: 0, position: "relative", height: chartHeight, bgcolor: "background.paper", borderRight: "1px solid rgba(255,255,255,0.06)", zIndex: 2 }}>
            {yTicks.map((tick) => {
              const isUpstream = hasUpstream && tick >= N + 1;
              const label = tick < N ? sortedInternal[tick]?.name : sortedUpstream[tick - N - 1]?.name;
              return (
                <Typography key={tick} sx={{ position: "absolute", top: rowCY(tick), right: 8, transform: "translateY(-50%)", fontSize: "0.68rem", lineHeight: 1, color: isUpstream ? "#8b949e" : "#c9d1d9", fontStyle: isUpstream ? "italic" : "normal", whiteSpace: "nowrap", maxWidth: Y_PANEL - 12, overflow: "hidden", textOverflow: "ellipsis", userSelect: "none" }}>
                  {label}
                </Typography>
              );
            })}
            {hasUpstream && (() => {
              const sepY = rowCY(N - 0.5 + 0.5);
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

          {/* Scrollable SVG */}
          <Box
            ref={scrollRef}
            sx={{
              overflowX: "auto",
              flex: 1,
              "&::-webkit-scrollbar": { height: 5 },
              "&::-webkit-scrollbar-track": { bgcolor: "rgba(255,255,255,0.03)" },
              "&::-webkit-scrollbar-thumb": {
                bgcolor: "rgba(255,255,255,0.18)",
                borderRadius: 3,
                "&:hover": { bgcolor: "rgba(255,255,255,0.32)" },
              },
            }}
          >
            <Box sx={{ width: dataWidth }}>
              <svg
                width={dataWidth}
                height={chartHeight}
                style={{ display: "block" }}
                onMouseLeave={() => { setTooltip(null); setHoveredBar(null); }}
              >
                {/* Alternating row fills */}
                {yTicks.map((tick, i) => (
                  <rect key={tick} x={0} y={rowCY(tick) - ROW_HEIGHT / 2} width={dataWidth} height={ROW_HEIGHT}
                    fill={i % 2 === 0 ? "rgba(255,255,255,0.013)" : "transparent"} />
                ))}

                {/* Vertical grid lines + X axis labels */}
                {xTicks.map(({ ms, label }, i) => {
                  const x = msToX(ms);
                  return (
                    <g key={i}>
                      <line x1={x} y1={gridY1} x2={x} y2={gridY2} stroke="rgba(255,255,255,0.05)" strokeWidth={1} />
                      <text x={x} y={labelY} textAnchor="middle" fill="#8b949e" fontSize={11} fontFamily="sans-serif">{label}</text>
                    </g>
                  );
                })}

                {/* X axis baseline */}
                <line x1={0} y1={gridY2} x2={PLOT_W} y2={gridY2} stroke="rgba(255,255,255,0.08)" strokeWidth={1} />

                {/* Internal / upstream separator */}
                {hasUpstream && (
                  <line x1={0} y1={rowCY(N - 0.5 + 0.5)} x2={PLOT_W} y2={rowCY(N - 0.5 + 0.5)}
                    stroke="rgba(255,255,255,0.08)" strokeDasharray="4 4" />
                )}

                {/* Fork / repo-start reference line */}
                {repoStartMs != null && repoStartMs >= startMs && (() => {
                  const fx = msToX(repoStartMs);
                  return (
                    <g>
                      {/* Category label — sits at the top of the reserved headroom */}
                      <text x={fx} y={gridY1 - 17} textAnchor="middle" fill="rgba(255,255,255,0.35)" fontSize={8} fontFamily="monospace">{repoStartLabel}</text>
                      {/* Exact date — just above the line start */}
                      <text x={fx} y={gridY1 - 5} textAnchor="middle" fill="rgba(255,255,255,0.55)" fontSize={9} fontFamily="monospace" fontWeight="bold">{fmtDateIso(repoStartMs)}</text>
                      <line x1={fx} y1={gridY1} x2={fx} y2={gridY2} stroke="rgba(255,255,255,0.5)" strokeWidth={1.5} strokeDasharray="6 3" />
                    </g>
                  );
                })()}

                {/* ── Activity bars (monthly mode) ── */}
                {activityBars.map((bar, i) => {
                  const x1    = msToX(bar.startMs);
                  const x2    = msToX(bar.endMs);
                  const w     = Math.max(4, x2 - x1); // always non-zero; bars span full months
                  const xRect = x1;
                  const cy    = rowCY(bar.yRow);
                  // pre-fork → gray  |  inactive post-fork → red  |  active → vivid green
                  const fill = bar.isPreFork
                    ? "#94a3b8"
                    : bar.isInactive
                      ? "#f87171"
                      : "#4ade80";
                  const baseOpacity = bar.isPreFork ? 0.5 : 0.88;
                  // Brighten hovered bar; dim all others when any bar is hovered
                  const opacity =
                    hoveredBar === null ? baseOpacity :
                    hoveredBar === i    ? Math.min(1, baseOpacity + 0.12) :
                                         baseOpacity * 0.3;
                  // date range string for tooltip
                  const d0 = new Date(bar.startMs);
                  const d1 = new Date(bar.endMs - 1);
                  const fmt = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
                  const range = bar.monthCount === 1 ? fmt(d0) : `${fmt(d0)} → ${fmt(d1)}`;
                  return (
                    <rect
                      key={i}
                      x={xRect} y={cy - BAR_H / 2}
                      width={w} height={BAR_H}
                      rx={3} ry={3}
                      fill={fill} opacity={opacity}
                      style={{ cursor: "default", transition: "opacity 0.1s" }}
                      onMouseEnter={(e) => {
                        setHoveredBar(i);
                        setTooltip({ clientX: e.clientX, clientY: e.clientY, devName: bar.devName, range, commits: bar.totalCommits, months: bar.monthCount, isUpstream: bar.isUpstream, isPreFork: bar.isPreFork });
                      }}
                      onMouseMove={(e) =>
                        setTooltip((prev) => prev ? { ...prev, clientX: e.clientX, clientY: e.clientY } : null)
                      }
                      onMouseLeave={() => {
                        setHoveredBar(null);
                        setTooltip(null);
                      }}
                    />
                  );
                })}

                {/* ── Fallback dots (no monthly history) ── */}
                {fallbackDots.map((dot, i) => (
                  <circle key={i} cx={dot.cx} cy={dot.cy} r={dot.r}
                    fill={dot.fill} opacity={dot.opacity}
                    stroke={dot.stroke} strokeWidth={dot.strokeWidth} />
                ))}

                {/* ── Global 60-day inactivity cutoff line ── */}
                {(() => {
                  const cutoffMs = Date.now() - 60 * 86_400_000;
                  if (cutoffMs < startMs) return null;
                  const cx = msToX(cutoffMs);
                  return (
                    <g>
                      <text x={cx} y={gridY1 - 17} textAnchor="middle"
                        fill="rgba(248,113,113,0.4)" fontSize={8} fontFamily="monospace">
                        inactivity cutoff
                      </text>
                      <text x={cx} y={gridY1 - 5} textAnchor="middle"
                        fill="rgba(248,113,113,0.6)" fontSize={9} fontFamily="monospace" fontWeight="bold">
                        {fmtDateIso(cutoffMs)}
                      </text>
                      <line x1={cx} y1={gridY1} x2={cx} y2={gridY2}
                        stroke="rgba(248,113,113,0.35)" strokeWidth={1} strokeDasharray="4 3" />
                    </g>
                  );
                })()}

                {/* ── Last-active markers + annotation ── */}
                {lastSeenMarkers.map((m, i) => {
                  const color = m.isInactive ? "#ea4335" : "#34a853";
                  return (
                    <g key={i}>
                      {/* Vertical tick */}
                      <rect x={m.x - 1} y={m.cy - 14} width={2} height={28}
                        fill={color} opacity={0.6} />
                      {/* Annotation to the right */}
                      <text
                        x={m.x + 5}
                        y={m.cy + 4}
                        fill={color}
                        fontSize={9}
                        fontFamily="monospace"
                        opacity={0.75}
                      >
                        {m.annotation}
                      </text>
                    </g>
                  );
                })}
              </svg>
            </Box>
          </Box>
        </Box>
      </Paper>

      {/* ── Floating tooltip ── */}
      {tooltip && (
        <Paper sx={{ position: "fixed", left: tooltip.clientX + 14, top: tooltip.clientY - 16, px: 1.5, py: 1, bgcolor: "#21262d", border: "1px solid rgba(255,255,255,0.1)", zIndex: 9999, pointerEvents: "none", boxShadow: "0 4px 16px rgba(0,0,0,0.5)" }}>
          <Typography variant="caption" sx={{ fontWeight: 600, display: "block" }}>{tooltip.devName}</Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", fontFamily: "monospace" }}>{tooltip.range}</Typography>
          <Typography variant="caption" color="text.disabled" sx={{ display: "block" }}>
            {tooltip.commits} commit{tooltip.commits !== 1 ? "s" : ""}
            {tooltip.months > 1 ? ` · ${tooltip.months} months` : ""}
            {" · "}{tooltip.isPreFork ? "upstream" : "internal"}
          </Typography>
        </Paper>
      )}

      {/* ── Module last-activity table ── */}
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
