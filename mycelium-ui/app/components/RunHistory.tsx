"use client";

import { useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Tooltip from "@mui/material/Tooltip";

import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import AccountTreeOutlinedIcon from "@mui/icons-material/AccountTreeOutlined";
import BiotechOutlinedIcon from "@mui/icons-material/BiotechOutlined";
import BoltOutlinedIcon from "@mui/icons-material/BoltOutlined";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import PlayArrowOutlinedIcon from "@mui/icons-material/PlayArrowOutlined";
import SchoolOutlinedIcon from "@mui/icons-material/SchoolOutlined";
import AssessmentOutlinedIcon from "@mui/icons-material/AssessmentOutlined";
import FolderOpenOutlinedIcon from "@mui/icons-material/FolderOpenOutlined";

import { fmt, timeAgo, fmtDatetime, type PipelineRun } from "./Pipeline";
import { scrollbarSx } from "../lib/sx";

type StageStatus = "pending" | "running" | "success" | "failed" | "skipped";

const STAGE_ORDER = [
  "observe_repo", "map_modules", "investigate",
  "observe_graph", "interpret", "plan", "act", "learn", "summary",
];
const STAGE_LABEL: Record<string, string> = {
  observe_repo:  "Observe",
  map_modules:   "Map",
  investigate:   "Investigate",
  observe_graph: "Graph",
  interpret:     "Interpret",
  plan:          "Plan",
  act:           "Execute",
  learn:         "Persist",
  summary:       "Summary",
};
const STAGE_ICON_EL: Record<string, React.ReactElement> = {
  observe_repo:  <VisibilityOutlinedIcon sx={{ fontSize: 12 }} />,
  map_modules:   <FolderOpenOutlinedIcon sx={{ fontSize: 12 }} />,
  investigate:   <BiotechOutlinedIcon sx={{ fontSize: 12 }} />,
  observe_graph: <AccountTreeOutlinedIcon sx={{ fontSize: 12 }} />,
  interpret:     <BoltOutlinedIcon sx={{ fontSize: 12 }} />,
  plan:          <AssignmentOutlinedIcon sx={{ fontSize: 12 }} />,
  act:           <PlayArrowOutlinedIcon sx={{ fontSize: 12 }} />,
  learn:         <SchoolOutlinedIcon sx={{ fontSize: 12 }} />,
  summary:       <AssessmentOutlinedIcon sx={{ fontSize: 12 }} />,
};

const CELL_BG: Record<StageStatus, string> = {
  pending: "rgba(255,255,255,0.05)",
  running: "#1a73e8",
  success: "#34a853",
  failed:  "#ea4335",
  skipped: "rgba(255,255,255,0.08)",
};

const RUN_DOT_COLOR: Record<string, string> = {
  success:   "#34a853",
  partial:   "#fbbc04",
  cancelled: "#fbbc04",
  failed:    "#ea4335",
  running:   "#1a73e8",
};

// Bar chart colors aligned with run status
const BAR_COLOR: Record<string, string> = {
  success:   "#34a853",
  partial:   "#fbbc04",
  cancelled: "#fbbc04",
  failed:    "#ea4335",
  running:   "#1a73e8",
};

const CHART_MAX_H = 64; // px — tallest bar height

const COL_W = 28;
const LABEL_W = 116;
const PAPER_BG = "#0d1117"; // matches MUI dark Paper background

function fmtTime(ts: number): string {
  return new Date(ts * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
}

function fmtDate(ts: number): string {
  return new Date(ts * 1000).toLocaleDateString([], { month: "short", day: "numeric" });
}

/** Total run duration in ms — uses summary.total_duration_ms when available,
 *  otherwise sums individual stage durations. Returns null for in-progress runs. */
function runDurationMs(run: PipelineRun): number | null {
  if (run.status === "running") return null;
  const summary = run.stages.find((s) => s.id === "summary");
  if (summary?.output && typeof summary.output.total_duration_ms === "number") {
    return summary.output.total_duration_ms as number;
  }
  const total = run.stages.reduce((acc, s) => acc + (s.duration_ms ?? 0), 0);
  return total > 0 ? total : null;
}

function GridCell({ status, duration_ms, error }: { status: StageStatus; duration_ms: number | null; error: string | null }) {
  return (
    <Tooltip
      title={
        <Stack spacing={0.25}>
          <Typography variant="caption" sx={{ fontWeight: 600, textTransform: "capitalize" }}>{status}</Typography>
          {duration_ms != null && <Typography variant="caption" color="text.secondary">{fmt(duration_ms)}</Typography>}
          {error && <Typography variant="caption" color="error.light" sx={{ maxWidth: 200, whiteSpace: "normal" }}>{error}</Typography>}
        </Stack>
      }
      placement="top"
      arrow
    >
      <Box
        sx={{
          width: COL_W - 8,
          height: 18,
          borderRadius: 0.5,
          bgcolor: CELL_BG[status] ?? "rgba(255,255,255,0.05)",
          flexShrink: 0,
          cursor: "default",
          "&:hover": { opacity: 0.75 },
        }}
      />
    </Tooltip>
  );
}

export default function RunHistory() {
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [tick, setTick] = useState(0);
  const scrollRef = useRef<HTMLDivElement>(null);
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  async function fetchHistory() {
    try {
      const res = await fetch(`${apiUrl}/pipeline/history`);
      if (res.ok) {
        const data = await res.json();
        setRuns(data.runs ?? []);
      }
    } catch {}
  }

  useEffect(() => {
    fetchHistory();
    const es = new EventSource(`${apiUrl}/pipeline/stream`);
    es.onmessage = (e) => {
      try {
        const run = JSON.parse(e.data) as PipelineRun;
        // Apply live SSE data immediately so the grid updates during a run.
        setRuns((prev) => {
          const idx = prev.findIndex((r) => r.run_id === run.run_id);
          if (idx >= 0) {
            const next = [...prev];
            next[idx] = run;
            return next;
          }
          return [...prev, run];
        });
        // Fetch full history from MongoDB once the run is done to pick up persisted data.
        if (run.status !== "running") fetchHistory();
      } catch {}
    };
    return () => es.close();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiUrl]);

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 5000);
    return () => clearInterval(id);
  }, []);

  // Auto-scroll to right (newest run) on update
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollLeft = scrollRef.current.scrollWidth;
    }
  }, [runs]);

  if (runs.length === 0) return null;

  const sorted = [...runs].sort((a, b) => a.started_at - b.started_at);

  const completed = sorted.filter((r) => r.status !== "running");
  const successes = completed.filter((r) => r.status === "success").length;
  const successRate = completed.length > 0 ? Math.round((successes / completed.length) * 100) : 0;
  const avgMs =
    completed.length > 0
      ? completed.reduce((acc, r) => {
          const s = r.stages.find((x) => x.id === "summary");
          const total = s?.output
            ? ((s.output.total_duration_ms as number) ?? 0)
            : r.stages.reduce((a, x) => a + (x.duration_ms ?? 0), 0);
          return acc + total;
        }, 0) / completed.length
      : 0;

  const rateColor = successRate >= 80 ? "success.main" : successRate >= 50 ? "warning.main" : "error.main";
  const stagesPresent = STAGE_ORDER.filter((id) => sorted.some((r) => r.stages.some((s) => s.id === id)));

  // Track date boundaries for grouping labels
  const dateLabels: Record<number, string> = {};
  let lastDate = "";
  sorted.forEach((run, i) => {
    const d = fmtDate(run.started_at);
    if (d !== lastDate) {
      dateLabels[i] = d;
      lastDate = d;
    }
  });

  return (
    <Stack spacing={1.5}>
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center" }}>
        <Typography variant="subtitle2" color="text.secondary">Run History</Typography>
        <Stack direction="row" spacing={2.5} sx={{ alignItems: "center" }}>
          <Typography variant="caption" color="text.disabled">
            <Typography component="span" variant="caption" color="text.primary" sx={{ fontWeight: 600 }}>{runs.length}</Typography> {runs.length === 1 ? "run" : "runs"}
          </Typography>
          <Typography variant="caption" color="text.disabled">
            <Typography component="span" variant="caption" color={rateColor} sx={{ fontWeight: 600 }}>{successRate}%</Typography> success
          </Typography>
          {avgMs > 0 && (
            <Typography variant="caption" color="text.disabled">
              avg <Typography component="span" variant="caption" color="text.primary" sx={{ fontWeight: 600 }}>{fmt(Math.round(avgMs))}</Typography>
            </Typography>
          )}
          <span style={{ display: "none" }}>{tick}</span>
        </Stack>
      </Stack>

      <Paper elevation={0} sx={{ p: 0, overflow: "hidden" }}>
        {/* Horizontally scrollable container */}
        <Box
          ref={scrollRef}
          sx={{ overflowX: "auto", pt: 2, pb: 2, pr: 2, pl: 0, ...scrollbarSx }}
        >
          {/* Date label row (offset by LABEL_W) */}
          <Box sx={{ display: "flex", pl: `${LABEL_W}px`, mb: 0.5, minWidth: "max-content", alignItems: "flex-end" }}>
            {sorted.map((run, i) => (
              <Box key={run.run_id} sx={{ width: COL_W, flexShrink: 0, display: "flex", justifyContent: "center", height: 52 }}>
                {dateLabels[i] && (
                  <Typography sx={{
                    fontSize: "0.58rem",
                    color: "rgba(255,255,255,0.45)",
                    lineHeight: 1.1,
                    whiteSpace: "nowrap",
                    fontWeight: 600,
                    writingMode: "vertical-rl",
                    transform: "rotate(180deg)",
                  }}>
                    {dateLabels[i]}
                  </Typography>
                )}
              </Box>
            ))}
          </Box>

          {/* Run status dots + time labels row */}
          <Box sx={{ display: "flex", pl: `${LABEL_W}px`, mb: 1, minWidth: "max-content", alignItems: "flex-end" }}>
            {sorted.map((run) => (
              <Tooltip
                key={run.run_id}
                title={
                  <Stack spacing={0.25}>
                    <Typography variant="caption" sx={{ fontWeight: 600, textTransform: "capitalize" }}>{run.status}</Typography>
                    <Typography variant="caption" color="text.secondary">{fmtDatetime(run.started_at)}</Typography>
                    <Typography variant="caption" color="text.disabled">{timeAgo(run.started_at)}</Typography>
                  </Stack>
                }
                placement="top"
                arrow
              >
                <Stack sx={{ width: COL_W, flexShrink: 0, alignItems: "center", cursor: "default", gap: 0.75 }}>
                  <Typography sx={{
                    fontSize: "0.55rem",
                    color: "rgba(255,255,255,0.22)",
                    lineHeight: 1,
                    whiteSpace: "nowrap",
                    writingMode: "vertical-rl",
                    transform: "rotate(180deg)",
                    letterSpacing: "0.02em",
                  }}>
                    {fmtTime(run.started_at)}
                  </Typography>
                  <Box
                    sx={{
                      width: 8,
                      height: 8,
                      borderRadius: "50%",
                      bgcolor: RUN_DOT_COLOR[run.status] ?? "rgba(255,255,255,0.2)",
                      boxShadow: run.status === "running" ? "0 0 0 3px rgba(26,115,232,0.25)" : "none",
                    }}
                  />
                </Stack>
              </Tooltip>
            ))}
          </Box>

          {/* Thin separator line */}
          <Box sx={{ pl: `${LABEL_W}px`, mb: 1, minWidth: "max-content" }}>
            <Box sx={{ height: 1, bgcolor: "rgba(255,255,255,0.06)" }} />
          </Box>

          {/* Stage rows - labels are sticky-left */}
          <Stack spacing={0.5} sx={{ minWidth: "max-content" }}>
            {stagesPresent.map((stageId) => (
              <Box key={stageId} sx={{ display: "flex", alignItems: "center", height: 22 }}>
                {/* Sticky label cell */}
                <Stack
                  direction="row"
                  spacing={0.75}
                  sx={{
                    position: "sticky",
                    left: 0,
                    width: LABEL_W,
                    flexShrink: 0,
                    alignItems: "center",
                    bgcolor: PAPER_BG,
                    pr: 1,
                    zIndex: 2,
                  }}
                >
                  <Box sx={{ color: "text.disabled", display: "flex", flexShrink: 0 }}>
                    {STAGE_ICON_EL[stageId]}
                  </Box>
                  <Typography variant="caption" color="text.disabled" noWrap sx={{ fontSize: "0.7rem" }}>
                    {STAGE_LABEL[stageId]}
                  </Typography>
                </Stack>

                {/* Grid cells */}
                {sorted.map((run) => {
                  const stage = run.stages.find((s) => s.id === stageId);
                  return (
                    <Box key={run.run_id} sx={{ width: COL_W, flexShrink: 0, display: "flex", justifyContent: "center" }}>
                      {stage ? (
                        <GridCell status={stage.status as StageStatus} duration_ms={stage.duration_ms} error={stage.error} />
                      ) : (
                        <Box sx={{ width: COL_W - 8, height: 18, borderRadius: 0.5, bgcolor: "rgba(255,255,255,0.02)" }} />
                      )}
                    </Box>
                  );
                })}
              </Box>
            ))}
          </Stack>

          {/* Legend */}
          <Stack direction="row" spacing={2} sx={{ mt: 2, pl: `${LABEL_W}px` }}>
            {(["success", "failed", "running", "skipped"] as StageStatus[]).map((s) => (
              <Stack key={s} direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
                <Box sx={{ width: 10, height: 10, borderRadius: 0.5, bgcolor: CELL_BG[s], border: "1px solid rgba(255,255,255,0.1)" }} />
                <Typography variant="caption" color="text.disabled" sx={{ textTransform: "capitalize", fontSize: "0.65rem" }}>{s}</Typography>
              </Stack>
            ))}
          </Stack>

          {/* Duration bar chart */}
          {(() => {
            const durations = sorted.map((r) => runDurationMs(r));
            const maxMs = Math.max(...durations.map((d) => d ?? 0), 1);
            const anyDuration = durations.some((d) => d != null);
            if (!anyDuration) return null;
            return (
              <>
                <Box sx={{ height: 1, bgcolor: "rgba(255,255,255,0.06)", mt: 2.5, ml: `${LABEL_W}px` }} />
                <Stack direction="row" spacing={0} sx={{ pl: `${LABEL_W}px`, mt: 0, alignItems: "flex-end", minWidth: "max-content" }}>
                  {/* Y-axis label */}
                  <Box sx={{ position: "sticky", left: 0, width: 0, overflow: "visible", zIndex: 2 }}>
                    <Typography sx={{
                      position: "absolute",
                      left: -LABEL_W,
                      bottom: 0,
                      width: LABEL_W - 8,
                      fontSize: "0.6rem",
                      color: "rgba(255,255,255,0.25)",
                      textAlign: "right",
                      lineHeight: 1,
                      pb: `${CHART_MAX_H / 2}px`,
                      userSelect: "none",
                    }}>
                      duration
                    </Typography>
                  </Box>
                  {sorted.map((run, i) => {
                    const ms = durations[i];
                    const barH = ms != null ? Math.max(3, Math.round((ms / maxMs) * CHART_MAX_H)) : 0;
                    const color = BAR_COLOR[run.status] ?? "rgba(255,255,255,0.15)";
                    return (
                      <Tooltip
                        key={run.run_id}
                        title={
                          ms != null ? (
                            <Stack spacing={0.25}>
                              <Typography variant="caption" sx={{ fontWeight: 600, textTransform: "capitalize" }}>{run.status}</Typography>
                              <Typography variant="caption" color="text.secondary">{fmt(ms)}</Typography>
                            </Stack>
                          ) : (
                            <Typography variant="caption" sx={{ textTransform: "capitalize" }}>{run.status}</Typography>
                          )
                        }
                        placement="top"
                        arrow
                      >
                        <Box sx={{
                          width: COL_W,
                          height: CHART_MAX_H,
                          display: "flex",
                          alignItems: "flex-end",
                          justifyContent: "center",
                          flexShrink: 0,
                          cursor: "default",
                        }}>
                          <Box sx={{
                            width: COL_W - 10,
                            height: barH,
                            bgcolor: color,
                            borderRadius: "2px 2px 0 0",
                            opacity: run.status === "running" ? 0.7 : 0.6,
                            transition: "height 0.3s ease",
                            "&:hover": { opacity: 1 },
                          }} />
                        </Box>
                      </Tooltip>
                    );
                  })}
                </Stack>
                {/* X-axis baseline */}
                <Box sx={{ height: 1, bgcolor: "rgba(255,255,255,0.1)", ml: `${LABEL_W}px` }} />
              </>
            );
          })()}
        </Box>
      </Paper>
    </Stack>
  );
}
