"use client";

import { useCallback, useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import BoltOutlinedIcon from "@mui/icons-material/BoltOutlined";
import CheckCircleOutlinedIcon from "@mui/icons-material/CheckCircleOutlined";
import ErrorOutlinedIcon from "@mui/icons-material/ErrorOutlined";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowRightIcon from "@mui/icons-material/KeyboardArrowRight";
import RefreshOutlinedIcon from "@mui/icons-material/RefreshOutlined";
import WarningAmberOutlinedIcon from "@mui/icons-material/WarningAmberOutlined";

import { fmt, fmtDatetime, timeAgo, type PipelineRun } from "./Pipeline";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ── types ─────────────────────────────────────────────────────────────────────

type Finding = {
  id: string;
  run_id?: string;
  concern_type: string;
  subject: string;
  narrative: string;
  recommended_actions?: string[];
  created_at?: string;
};

type Action = {
  id?: string;
  run_id: string;
  tool: string;
  detail: string;
  success: boolean;
  executed_at?: string;
};

type RunEntry = {
  run: PipelineRun;
  findings: Finding[];
  actions: Action[];
  totalMs: number | null;
};

// ── helpers ───────────────────────────────────────────────────────────────────

function groupByDate(entries: RunEntry[]): { label: string; entries: RunEntry[] }[] {
  const groups: Record<string, RunEntry[]> = {};
  for (const e of entries) {
    const d = new Date(e.run.started_at * 1000);
    const today = new Date();
    const yesterday = new Date(today);
    yesterday.setDate(today.getDate() - 1);

    let label: string;
    if (d.toDateString() === today.toDateString()) {
      label = "Today";
    } else if (d.toDateString() === yesterday.toDateString()) {
      label = "Yesterday";
    } else {
      label = d.toLocaleDateString([], { weekday: "long", month: "short", day: "numeric" });
    }
    if (!groups[label]) groups[label] = [];
    groups[label].push(e);
  }
  return Object.entries(groups).map(([label, entries]) => ({ label, entries }));
}

const CONCERN_COLOR: Record<string, string> = {
  knowledge_concentration:    "#ea4335",
  fading_contributor:         "#ea4335",
  sole_contributor:           "#fbbc04",
  recent_joiner_exposure:     "#1a73e8",
  onboarding_isolation:       "#1a73e8",
  undeclared_ownership:       "#fbbc04",
  nominal_ownership:          "#fbbc04",
  fragile_documentation:      "#9c27b0",
  upstream_dominance:         "#00bcd4",
  upstream_drift:             "#00bcd4",
  stalled_work:               "#fbbc04",
  ci_instability:             "#ea4335",
};

function concernColor(type: string) {
  return CONCERN_COLOR[type] ?? "rgba(255,255,255,0.4)";
}

const ACTION_LABEL: Record<string, string> = {
  create_issue:                "Issue created",
  assign_issue:                "Issue assigned",
  add_comment:                 "Comment added",
  generate_onboarding_pack:    "Onboarding pack",
  generate_offboarding_artifact: "Offboarding artifact",
};

// ── RunEntry row ──────────────────────────────────────────────────────────────

function RunRow({ entry }: { entry: RunEntry }) {
  const { run, findings, actions, totalMs } = entry;
  const [open, setOpen] = useState(false);

  const statusColor =
    run.status === "success" ? "#34a853"
    : run.status === "failed" ? "#ea4335"
    : run.status === "running" ? "#1a73e8"
    : "#fbbc04";

  const StatusIcon =
    run.status === "success" ? CheckCircleOutlinedIcon
    : run.status === "failed" ? ErrorOutlinedIcon
    : WarningAmberOutlinedIcon;

  return (
    <Box>
      {/* Run header row */}
      <Box
        onClick={() => setOpen((o) => !o)}
        sx={{
          display: "flex",
          alignItems: "flex-start",
          gap: 2,
          px: 2,
          py: 1.5,
          cursor: "pointer",
          "&:hover": { bgcolor: "rgba(255,255,255,0.02)" },
          transition: "background 0.12s",
        }}
      >
        {/* Timeline spine */}
        <Box sx={{ display: "flex", flexDirection: "column", alignItems: "center", flexShrink: 0, pt: 0.5 }}>
          <StatusIcon sx={{ fontSize: 16, color: statusColor }} />
          {(findings.length > 0 || actions.length > 0) && open && (
            <Box sx={{ width: 1, flex: 1, bgcolor: "rgba(255,255,255,0.08)", mt: 0.5, minHeight: 20 }} />
          )}
        </Box>

        {/* Content */}
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Stack direction="row" spacing={1.5} sx={{ alignItems: "center", flexWrap: "wrap", mb: 0.25 }}>
            <Typography variant="body2" sx={{ fontFamily: "monospace", fontWeight: 600, color: statusColor }}>
              {run.status.toUpperCase()}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {fmtDatetime(run.started_at)}
            </Typography>
            {totalMs != null && (
              <Typography variant="caption" color="text.disabled">
                · {fmt(totalMs)}
              </Typography>
            )}
            <Typography variant="caption" color="text.disabled" sx={{ fontFamily: "monospace", fontSize: "0.65rem" }}>
              {run.run_id.slice(0, 8)}
            </Typography>
          </Stack>

          {/* Summary chips */}
          <Stack direction="row" spacing={0.75} sx={{ flexWrap: "wrap" }} useFlexGap>
            {findings.length > 0 && (
              <Chip
                label={`${findings.length} finding${findings.length !== 1 ? "s" : ""}`}
                size="small"
                sx={{ height: 18, fontSize: "0.62rem", bgcolor: "rgba(234,67,53,0.1)", color: "#ea4335", border: "none", "& .MuiChip-label": { px: 0.75 } }}
              />
            )}
            {actions.length > 0 && (
              <Chip
                label={`${actions.length} action${actions.length !== 1 ? "s" : ""}`}
                size="small"
                sx={{ height: 18, fontSize: "0.62rem", bgcolor: "rgba(52,168,83,0.1)", color: "#34a853", border: "none", "& .MuiChip-label": { px: 0.75 } }}
              />
            )}
            {findings.length === 0 && actions.length === 0 && run.status === "success" && (
              <Typography variant="caption" color="text.disabled">No findings — repository healthy</Typography>
            )}
          </Stack>
        </Box>

        {/* Expand toggle */}
        {(findings.length > 0 || actions.length > 0) && (
          <Box sx={{ color: "text.disabled", flexShrink: 0, mt: 0.25 }}>
            {open ? <KeyboardArrowDownIcon sx={{ fontSize: 16 }} /> : <KeyboardArrowRightIcon sx={{ fontSize: 16 }} />}
          </Box>
        )}
      </Box>

      {/* Expanded detail */}
      <Collapse in={open && (findings.length > 0 || actions.length > 0)} unmountOnExit>
        <Box sx={{ pl: "40px", pr: 2, pb: 1.5 }}>
          <Stack spacing={2}>
            {/* Findings */}
            {findings.length > 0 && (
              <Box>
                <Typography variant="caption" color="text.disabled" sx={{ display: "block", mb: 1, textTransform: "uppercase", letterSpacing: "0.08em", fontSize: "0.62rem" }}>
                  Findings
                </Typography>
                <Stack spacing={0.75}>
                  {findings.map((f) => (
                    <Paper
                      key={f.id}
                      elevation={0}
                      sx={{
                        px: 1.5,
                        py: 1,
                        bgcolor: "rgba(255,255,255,0.02)",
                        border: `1px solid ${concernColor(f.concern_type)}22`,
                        borderLeft: `2px solid ${concernColor(f.concern_type)}`,
                        borderRadius: 1.5,
                      }}
                    >
                      <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 0.5 }}>
                        <Chip
                          label={f.concern_type.replace(/_/g, " ")}
                          size="small"
                          sx={{
                            height: 18,
                            fontSize: "0.6rem",
                            bgcolor: `${concernColor(f.concern_type)}18`,
                            color: concernColor(f.concern_type),
                            border: "none",
                            "& .MuiChip-label": { px: 0.75 },
                          }}
                        />
                        <Typography variant="caption" sx={{ fontFamily: "monospace", fontWeight: 600, color: "text.primary" }}>
                          {f.subject}
                        </Typography>
                      </Stack>
                      <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.5, display: "block" }}>
                        {f.narrative?.slice(0, 200)}{(f.narrative?.length ?? 0) > 200 ? "…" : ""}
                      </Typography>
                    </Paper>
                  ))}
                </Stack>
              </Box>
            )}

            {/* Actions */}
            {actions.length > 0 && (
              <Box>
                <Typography variant="caption" color="text.disabled" sx={{ display: "block", mb: 1, textTransform: "uppercase", letterSpacing: "0.08em", fontSize: "0.62rem" }}>
                  Actions taken
                </Typography>
                <Stack spacing={0.5}>
                  {actions.map((a, i) => (
                    <Stack key={i} direction="row" spacing={1} sx={{ alignItems: "flex-start" }}>
                      <BoltOutlinedIcon sx={{ fontSize: 13, color: a.success ? "#34a853" : "#ea4335", mt: 0.2, flexShrink: 0 }} />
                      <Box>
                        <Typography variant="caption" sx={{ fontWeight: 600, color: a.success ? "text.primary" : "error.main" }}>
                          {ACTION_LABEL[a.tool] ?? a.tool}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ display: "block", lineHeight: 1.4 }}>
                          {a.detail}
                        </Typography>
                      </Box>
                    </Stack>
                  ))}
                </Stack>
              </Box>
            )}
          </Stack>
        </Box>
      </Collapse>

      <Divider sx={{ borderColor: "rgba(255,255,255,0.04)" }} />
    </Box>
  );
}

// ── main component ────────────────────────────────────────────────────────────

export default function Timeline() {
  const [entries, setEntries] = useState<RunEntry[]>([]);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [runsRes, findingsRes, actionsRes] = await Promise.all([
        fetch(`${API}/pipeline/history`),
        fetch(`${API}/findings?limit=500`),
        fetch(`${API}/actions?limit=500`),
      ]);
      const runsData = await runsRes.json();
      const findingsData = findingsRes.ok ? await findingsRes.json() : [];
      const actionsData = actionsRes.ok ? await actionsRes.json() : [];

      const runs: PipelineRun[] = (runsData.runs ?? runsData ?? []) as PipelineRun[];
      const findings: Finding[] = Array.isArray(findingsData) ? findingsData : (findingsData.findings ?? []);
      const actions: Action[] = Array.isArray(actionsData) ? actionsData : (actionsData.actions ?? []);

      // Group findings and actions by run_id
      const findingsByRun: Record<string, Finding[]> = {};
      for (const f of findings) {
        if (!f.run_id) continue;
        if (!findingsByRun[f.run_id]) findingsByRun[f.run_id] = [];
        findingsByRun[f.run_id].push(f);
      }
      const actionsByRun: Record<string, Action[]> = {};
      for (const a of actions) {
        if (!a.run_id) continue;
        if (!actionsByRun[a.run_id]) actionsByRun[a.run_id] = [];
        actionsByRun[a.run_id].push(a);
      }

      const built: RunEntry[] = runs.map((run) => {
        const summaryStage = run.stages.find((s) => s.id === "summary");
        const totalMs = summaryStage?.output
          ? (summaryStage.output.total_duration_ms as number | null) ?? null
          : run.stages.reduce((a, s) => a + (s.duration_ms ?? 0), 0) || null;
        return {
          run,
          findings: findingsByRun[run.run_id] ?? [],
          actions: actionsByRun[run.run_id] ?? [],
          totalMs,
        };
      }).sort((a, b) => b.run.started_at - a.run.started_at);

      setEntries(built);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const groups = groupByDate(entries);
  const totalFindings = entries.reduce((a, e) => a + e.findings.length, 0);
  const totalActions = entries.reduce((a, e) => a + e.actions.length, 0);

  return (
    <Stack spacing={2}>
      {/* Header stats */}
      <Stack direction="row" spacing={3} sx={{ alignItems: "center" }}>
        <Stack direction="row" spacing={1}>
          <Typography variant="caption" color="text.disabled">{entries.length} runs</Typography>
          {totalFindings > 0 && <Typography variant="caption" color="text.disabled">· {totalFindings} findings</Typography>}
          {totalActions > 0 && <Typography variant="caption" color="text.disabled">· {totalActions} actions</Typography>}
        </Stack>
        <Box sx={{ flex: 1 }} />
        <IconButton size="small" onClick={load} sx={{ color: "text.disabled" }}>
          <RefreshOutlinedIcon sx={{ fontSize: 16 }} />
        </IconButton>
      </Stack>

      {loading ? (
        <Box sx={{ display: "flex", justifyContent: "center", py: 6 }}>
          <CircularProgress size={24} />
        </Box>
      ) : entries.length === 0 ? (
        <Paper variant="outlined" sx={{ p: 4, textAlign: "center", borderColor: "rgba(255,255,255,0.08)" }}>
          <Typography variant="body2" color="text.disabled">
            No pipeline runs yet. Use <Box component="code" sx={{ fontFamily: "monospace", bgcolor: "rgba(255,255,255,0.06)", px: 0.5, borderRadius: 0.5 }}>Run Now</Box> on the Pipeline page to start one.
          </Typography>
        </Paper>
      ) : (
        <Paper variant="outlined" sx={{ borderColor: "rgba(255,255,255,0.08)", borderRadius: 2, overflow: "hidden" }}>
          {groups.map(({ label, entries: groupEntries }, gi) => (
            <Box key={label}>
              {/* Date group header */}
              <Box sx={{ px: 2, py: 0.75, bgcolor: "rgba(255,255,255,0.02)", borderBottom: "1px solid rgba(255,255,255,0.05)" }}>
                <Typography variant="caption" color="text.disabled" sx={{ fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em", fontSize: "0.62rem" }}>
                  {label}
                </Typography>
              </Box>
              {groupEntries.map((entry) => (
                <RunRow key={entry.run.run_id} entry={entry} />
              ))}
              {gi < groups.length - 1 && <Divider sx={{ borderColor: "rgba(255,255,255,0.06)" }} />}
            </Box>
          ))}
        </Paper>
      )}
    </Stack>
  );
}
