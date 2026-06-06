// Copyright 2026 Javier Huang
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

"use client";

import { useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import Typography from "@mui/material/Typography";
import Button from "@mui/material/Button";
import Stack from "@mui/material/Stack";
import LinearProgress from "@mui/material/LinearProgress";
import Paper from "@mui/material/Paper";
import Grid from "@mui/material/Grid";

import VisibilityOutlinedIcon from "@mui/icons-material/VisibilityOutlined";
import AccountTreeOutlinedIcon from "@mui/icons-material/AccountTreeOutlined";
import BoltOutlinedIcon from "@mui/icons-material/BoltOutlined";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import PlayArrowOutlinedIcon from "@mui/icons-material/PlayArrowOutlined";
import StopOutlinedIcon from "@mui/icons-material/StopOutlined";
import SchoolOutlinedIcon from "@mui/icons-material/SchoolOutlined";
import AssessmentOutlinedIcon from "@mui/icons-material/AssessmentOutlined";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import FiberManualRecordIcon from "@mui/icons-material/FiberManualRecord";
import LoopIcon from "@mui/icons-material/Loop";
import CheckCircleOutlinedIcon from "@mui/icons-material/CheckCircleOutlined";
import ErrorOutlinedIcon from "@mui/icons-material/ErrorOutlined";
import AccessTimeIcon from "@mui/icons-material/AccessTime";
import FolderOpenOutlinedIcon from "@mui/icons-material/FolderOpenOutlined";
import BiotechOutlinedIcon from "@mui/icons-material/BiotechOutlined";
import Md from "./Md";
import AgentTrace, { type TraceEvent } from "./AgentTrace";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
type StageStatus = "pending" | "running" | "success" | "failed" | "skipped" | "cancelled";

type Stage = {
  id: string;
  label: string;
  description: string;
  status: StageStatus;
  started_at: number | null;
  duration_ms: number | null;
  output: Record<string, unknown> | null;
  error: string | null;
};

export type PipelineRun = {
  run_id: string;
  started_at: number;
  status: string;
  stages: Stage[];
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
export function fmt(ms: number | null) {
  if (ms == null) return null;
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(1)}s`;
}

export function timeAgo(ts: number) {
  const diff = Math.floor(Date.now() / 1000 - ts);
  if (diff < 5) return "just now";
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

export function fmtDatetime(ts: number): string {
  const d = new Date(ts * 1000);
  const date = d.toLocaleDateString([], { month: "short", day: "numeric" });
  const time = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  return `${date} · ${time}`;
}

const STATUS_COLOR: Record<StageStatus, "default" | "primary" | "success" | "error" | "warning"> = {
  pending: "default",
  running: "primary",
  success: "success",
  failed: "error",
  skipped: "default",
  cancelled: "warning",
};

const STATUS_LABEL: Record<StageStatus, string> = {
  pending: "Pending",
  running: "Running",
  success: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
  skipped: "Skipped",
};

/** Pluralize: n(3, "module") → "3 modules", n(1, "module") → "1 module" */
function n(count: number, word: string, pluralForm?: string): string {
  return `${count} ${count === 1 ? word : (pluralForm ?? word + "s")}`;
}

// Icon hints for well-known stage IDs. Both current names and anticipated
// renamed equivalents are listed so renaming stages doesn't break the UI.
// Unknown IDs fall back to <AccessTimeIcon /> at the call site.
export const STAGE_ICONS: Record<string, React.ReactElement> = {
  observe_repo:  <VisibilityOutlinedIcon fontSize="small" />,
  observe:       <VisibilityOutlinedIcon fontSize="small" />,
  map_modules:   <FolderOpenOutlinedIcon fontSize="small" />,
  model:         <FolderOpenOutlinedIcon fontSize="small" />,
  investigate:   <BiotechOutlinedIcon fontSize="small" />,
  analyze:       <BiotechOutlinedIcon fontSize="small" />,
  observe_graph: <AccountTreeOutlinedIcon fontSize="small" />,
  interpret:     <BoltOutlinedIcon fontSize="small" />,
  plan:          <AssignmentOutlinedIcon fontSize="small" />,
  decide:        <AssignmentOutlinedIcon fontSize="small" />,
  act:           <PlayArrowOutlinedIcon fontSize="small" />,
  reflect:       <LoopIcon fontSize="small" />,
  learn:         <SchoolOutlinedIcon fontSize="small" />,
  persist:       <SchoolOutlinedIcon fontSize="small" />,
  summary:       <AssessmentOutlinedIcon fontSize="small" />,
};

// ---------------------------------------------------------------------------
// Inline stage summary (single line, key metrics)
// ---------------------------------------------------------------------------
function stageSummary(stage: Stage): string | null {
  if (!stage.output) return stage.description ?? null;
  const o = stage.output;
  switch (stage.id.replace(/_\d+$/, "")) {
    // Current stage IDs
    case "observe":
      return `${n(o.commit_contributors as number ?? 0, "contributor")} · ${o.upstream_authors ?? 0} upstream · ${o.open_issues ?? 0} open issues`;
    case "model":
      return `${n(o.modules_discovered as number ?? 0, "module")} · ${n(o.total_attributions as number ?? 0, "author attribution")}`;
    case "analyze": {
      const members = o.member_investigations as number ?? 0;
      const modules = o.module_investigations as number ?? 0;
      const findings = o.finding_count as number ?? 0;
      return `${n(members, "member")} · ${n(modules, "module")} investigated · ${n(findings, "finding")}`;
    }
    case "decide": {
      const planned = o.actions_planned as number ?? 0;
      const deduped = o.actions_deduplicated as number ?? 0;
      let s = `${n(planned, "action")} planned`;
      if (deduped > 0) s += ` · ${deduped} deduplicated`;
      return s;
    }
    case "act": {
      const executed = o.executed as number ?? 0;
      const failed = o.failed as number ?? 0;
      const passes = o.stabilization_passes as number ?? 1;
      const stale = o.stale_issues_closed as number ?? 0;
      let s = `${executed} executed · ${failed} failed`;
      if (passes > 1) s += ` · ${passes} passes`;
      if (stale > 0) s += ` · ${stale} stale closed`;
      return s;
    }
    case "reflect": {
      const actioned = o.findings_actioned as number ?? 0;
      const preExisting = o.findings_pre_existing as number ?? 0;
      const unaddressed = o.findings_unaddressed as number ?? 0;
      return `${actioned} actioned · ${preExisting} pre-existing · ${unaddressed} unaddressed`;
    }
    case "persist":
      return `${o.updated ?? 0}/${o.total ?? 0} records · ${n(o.findings_saved as number ?? 0, "finding")} saved`;
    case "summary":
      return `${o.stages_succeeded ?? 0}/${o.stages_total ?? 0} stages · ${fmt(o.total_duration_ms as number)}`;
    default:
      return null;
  }
}

// ---------------------------------------------------------------------------
// Shared sub-components
// ---------------------------------------------------------------------------
function MetricCard({ label, value, highlight = false }: { label: string; value: unknown; highlight?: boolean }) {
  return (
    <Paper elevation={0} sx={{ p: 2, bgcolor: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 2 }}>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
        {label}
      </Typography>
      <Typography variant="h5" sx={{ fontWeight: 600, mt: 0.5, color: highlight ? "error.main" : "text.primary" }}>
        {String(value ?? "-")}
      </Typography>
    </Paper>
  );
}

// ---------------------------------------------------------------------------
// Detail panels
// ---------------------------------------------------------------------------
function ObserveRepoDetail({ output }: { output: Record<string, unknown> }) {
  const upstreamList = (output.upstream_author_list as Array<Record<string, unknown>>) ?? [];
  const failingUrls = (output.failing_pipeline_urls as string[]) ?? [];
  return (
    <Stack spacing={2}>
      <Grid container spacing={2}>
        <Grid size={4}><MetricCard label="Members" value={output.members} /></Grid>
        <Grid size={4}><MetricCard label="Open Issues" value={output.open_issues} /></Grid>
        <Grid size={4}><MetricCard label="Open MRs" value={output.open_mrs} /></Grid>
        <Grid size={4}><MetricCard label="Commit Contributors" value={output.commit_contributors} /></Grid>
        <Grid size={4}><MetricCard label="Upstream Authors" value={output.upstream_authors} highlight={(output.upstream_authors as number) > 0} /></Grid>
        <Grid size={4}><MetricCard label="CODEOWNERS Entries" value={output.codeowners_entries} /></Grid>
        <Grid size={4}><MetricCard label="Pipelines Passing" value={output.pipeline_passing} /></Grid>
        <Grid size={4}><MetricCard label="Pipelines Failing" value={output.pipeline_failing} highlight={(output.pipeline_failing as number) > 0} /></Grid>
        <Grid size={4}><MetricCard label="MR Approvers" value={output.mr_approvers_tracked} /></Grid>
      </Grid>
      {failingUrls.length > 0 && (
        <Box>
          <Typography variant="caption" color="error.main" sx={{ display: "block", mb: 0.75 }}>
            Failing pipelines
          </Typography>
          <Stack spacing={0.5}>
            {failingUrls.map((url, i) => (
              <Typography key={i} variant="caption" sx={{ fontFamily: "var(--font-google-sans-code)", color: "error.light", opacity: 0.8 }}>
                {url}
              </Typography>
            ))}
          </Stack>
        </Box>
      )}
      {upstreamList.length > 0 && (
        <Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
            Upstream authors (in commit history, not current members)
          </Typography>
          <Stack spacing={0.5}>
            {upstreamList.map((c, i) => (
              <Stack key={i} direction="row" spacing={1} sx={{ alignItems: "center" }}>
                <Chip label="upstream" size="small" color="warning" variant="outlined" sx={{ height: 20, fontSize: "0.65rem" }} />
                <Typography variant="body2">{String(c.name ?? "")}</Typography>
                {!!c.email && <Typography variant="caption" color="text.secondary">{String(c.email)}</Typography>}
              </Stack>
            ))}
          </Stack>
        </Box>
      )}
    </Stack>
  );
}

function MapModulesDetail({ output }: { output: Record<string, unknown> }) {
  const paths = (output.module_paths as string[]) ?? [];
  return (
    <Stack spacing={2}>
      <Grid container spacing={2}>
        <Grid size={4}><MetricCard label="Modules Discovered" value={output.modules_discovered} highlight={(output.modules_discovered as number) > 0} /></Grid>
        <Grid size={4}><MetricCard label="Author Attributions" value={output.total_attributions} /></Grid>
      </Grid>
      {paths.length > 0 && (
        <Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.75 }}>
            Knowledge areas mapped
          </Typography>
          <Stack direction="row" spacing={0.75} sx={{ flexWrap: "wrap" }} useFlexGap>
            {paths.map((p) => (
              <Chip key={p} label={p} size="small" variant="outlined" sx={{ fontFamily: "var(--font-google-sans-code)", height: 20, fontSize: "0.65rem" }} />
            ))}
          </Stack>
        </Box>
      )}
      {paths.length === 0 && (
        <Typography variant="body2" color="text.disabled">No code directories found in repository root</Typography>
      )}
    </Stack>
  );
}

function InvestigateDetail({ output }: { output: Record<string, unknown> }) {
  const memberCount = (output.member_investigations as number) ?? 0;
  const moduleCount = (output.module_investigations as number) ?? 0;
  const driftInvestigated = output.drift_investigated as boolean;
  const members = (output.members as Array<Record<string, unknown>>) ?? [];
  const modules = (output.modules as Array<Record<string, unknown>>) ?? [];

  if (memberCount === 0 && moduleCount === 0 && !driftInvestigated) {
    const noModules = (output.modules as Array<unknown>)?.length === 0 || moduleCount === 0;
    return (
      <Stack spacing={1.5}>
        <Grid container spacing={2}>
          <Grid size={4}><MetricCard label="Member Investigations" value={0} /></Grid>
          <Grid size={4}><MetricCard label="Module Investigations" value={0} /></Grid>
          <Grid size={4}><MetricCard label="Drift" value="No" /></Grid>
        </Grid>
        <Typography variant="body2" color="text.disabled">
          {noModules
            ? "No code directories were discovered. No investigators were spawned. Check that the pipeline service account has repository read access."
            : "No high-attention members or modules flagged this run. No investigators were spawned."}
        </Typography>
      </Stack>
    );
  }

  return (
    <Stack spacing={2}>
      <Grid container spacing={2}>
        <Grid size={4}><MetricCard label="Member Investigations" value={memberCount} highlight={memberCount > 0} /></Grid>
        <Grid size={4}><MetricCard label="Module Investigations" value={moduleCount} /></Grid>
        <Grid size={4}><MetricCard label="Drift Investigated" value={driftInvestigated ? "Yes" : "No"} /></Grid>
      </Grid>

      {members.length > 0 && (
        <Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.75, textTransform: "uppercase", letterSpacing: "0.08em", fontSize: "0.65rem" }}>
            High-attention members
          </Typography>
          <Stack spacing={0.75}>
            {members.map((m, i) => (
              <Paper key={i} elevation={0} sx={{ p: 1.5, bgcolor: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 1.5 }}>
                <Stack direction="row" spacing={1} sx={{ alignItems: "center", mb: 0.5 }}>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>{String(m.member ?? "")}</Typography>
                  <Chip label={String(m.attention_reason ?? "").replace(/_/g, " ")} size="small" variant="outlined"
                    sx={{ height: 20, fontSize: "0.65rem" }} />
                </Stack>
                {!!m.urgency_reasoning && (
                  <Md>{String(m.urgency_reasoning)}</Md>
                )}
              </Paper>
            ))}
          </Stack>
        </Box>
      )}

      {modules.length > 0 && (
        <Box>
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.75, textTransform: "uppercase", letterSpacing: "0.08em", fontSize: "0.65rem" }}>
            Module investigations
          </Typography>
          <Stack direction="row" spacing={0.75} sx={{ flexWrap: "wrap" }} useFlexGap>
            {modules.map((m, i) => {
              const state = String(m.documentation_state ?? "");
              const stateColor = state === "excellent" ? "#34a853" : state === "adequate" ? "#8ab4f8" : state === "sparse" ? "#fbbc04" : state === "missing" || state === "placeholder" ? "#ea4335" : "text.disabled";
              return (
                <Chip key={i}
                  label={`${String(m.module ?? "")}${state ? ` · ${state}` : ""}`}
                  size="small" variant="outlined"
                  sx={{ height: 22, fontSize: "0.7rem", fontFamily: "var(--font-google-sans-code)", color: stateColor, borderColor: `${stateColor}55` }} />
              );
            })}
          </Stack>
        </Box>
      )}
    </Stack>
  );
}

function PlanDetail({ output }: { output: Record<string, unknown> }) {
  const actions = (output.actions as Array<Record<string, unknown>>) ?? [];
  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={2}>
        <Typography variant="body2" color="text.secondary">
          <Box component="span" sx={{ color: "text.primary", fontWeight: 600 }}>{String(output.actions_planned)}</Box> actions planned
        </Typography>
        <Typography variant="body2" color="text.secondary">
          <Box component="span" sx={{ color: "text.primary", fontWeight: 600 }}>{String(output.graph_updates_planned)}</Box> graph updates
        </Typography>
      </Stack>
      {actions.length > 0 ? (
        <Stack spacing={1}>
          {actions.map((a, i) => (
            <Paper key={i} elevation={0} sx={{ p: 1.5, bgcolor: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 1.5, display: "flex", alignItems: "flex-start", gap: 1.5 }}>
              <Chip label={String(a.kind ?? "")} size="small" variant="outlined" sx={{ fontFamily: "var(--font-google-sans-code)", height: 22, fontSize: "0.7rem" }} />
              <Typography variant="body2" color="text.secondary">
                {String((a.params as Record<string, unknown>)?.title ?? JSON.stringify(a.params ?? {}))}
              </Typography>
            </Paper>
          ))}
        </Stack>
      ) : (
        <Typography variant="body2" color="text.disabled">No actions planned</Typography>
      )}
    </Stack>
  );
}

function ActDetail({ output }: { output: Record<string, unknown> }) {
  const details = (output.details as Array<Record<string, unknown>>) ?? [];
  const trace = (output.trace as TraceEvent[] | undefined) ?? [];
  const violations = (output.boundary_violations as string[]) ?? [];

  return (
    <Stack spacing={2}>
      <Stack direction="row" spacing={2}>
        <Typography variant="body2" color="text.secondary">
          <Box component="span" sx={{ color: "success.main", fontWeight: 600 }}>{String(output.executed)}</Box> executed
        </Typography>
        <Typography variant="body2" color="text.secondary">
          <Box component="span" sx={{ color: (output.failed as number) > 0 ? "error.main" : "text.disabled", fontWeight: 600 }}>{String(output.failed)}</Box> failed
        </Typography>
      </Stack>

      {violations.length > 0 && (
        <Box>
          <Typography variant="caption" color="error.main" sx={{ display: "block", mb: 0.5, fontWeight: 600 }}>
            ⚠ Ownership boundary violations detected
          </Typography>
          <Stack spacing={0.5}>
            {violations.map((v, i) => (
              <Typography key={i} variant="caption" sx={{ fontFamily: "var(--font-google-sans-code)", color: "error.light", fontSize: "0.68rem" }}>
                {v}
              </Typography>
            ))}
          </Stack>
        </Box>
      )}

      {details.length > 0 ? (
        <Stack spacing={0.75}>
          {details.map((d, i) => (
            <Stack key={i} direction="row" spacing={1} sx={{ alignItems: "center" }}>
              <CheckCircleOutlinedIcon sx={{ fontSize: 14, color: "success.main" }} />
              <Chip label={String(d.kind ?? "")} size="small" variant="outlined" sx={{ fontFamily: "var(--font-google-sans-code)", height: 20, fontSize: "0.7rem" }} />
              <Typography variant="body2" color="text.secondary">{String(d.detail ?? "")}</Typography>
            </Stack>
          ))}
        </Stack>
      ) : (
        <Typography variant="body2" color="text.disabled">No actions executed</Typography>
      )}

      {trace.length > 0 && (
        <Box sx={{ borderTop: "1px solid rgba(255,255,255,0.06)", pt: 2 }}>
          <AgentTrace events={trace} />
        </Box>
      )}
    </Stack>
  );
}

function LearnDetail({ output }: { output: Record<string, unknown> }) {
  const busFactorRefreshed = (output.modules_bus_factor_refreshed as number) ?? 0;
  const findingsSaved = (output.findings_saved as number) ?? 0;
  return (
    <Stack spacing={2}>
      <Grid container spacing={2}>
        <Grid size={4}>
          <MetricCard label="Records Updated" value={`${output.updated ?? 0}/${output.total ?? 0}`} />
        </Grid>
        <Grid size={4}>
          <MetricCard label="Bus Factor Refreshed" value={busFactorRefreshed} />
        </Grid>
        <Grid size={4}>
          <MetricCard label="Findings Saved" value={findingsSaved} highlight={findingsSaved > 0} />
        </Grid>
      </Grid>
    </Stack>
  );
}

function ReflectDetail({ output }: { output: Record<string, unknown> }) {
  const actioned    = (output.findings_actioned    as number) ?? 0;
  const preExisting = (output.findings_pre_existing as number) ?? 0;
  const unaddressed = (output.findings_unaddressed  as number) ?? 0;
  const total       = (output.findings_total        as number) ?? 0;
  const newIids     = (output.newly_created_iids    as number[]) ?? [];
  const missed      = (output.unaddressed_subjects  as string[]) ?? [];
  return (
    <Stack spacing={2}>
      <Grid container spacing={2}>
        <Grid size={3}><MetricCard label="Findings Total"     value={total}       /></Grid>
        <Grid size={3}><MetricCard label="Actioned"           value={actioned}     highlight={actioned > 0} /></Grid>
        <Grid size={3}><MetricCard label="Pre-existing"       value={preExisting}  /></Grid>
        <Grid size={3}><MetricCard label="Unaddressed"        value={unaddressed}  highlight={unaddressed > 0} /></Grid>
      </Grid>
      {newIids.length > 0 && (
        <Typography variant="caption" color="text.secondary">
          Confirmed new issues: {newIids.map(id => `#${id}`).join(", ")}
        </Typography>
      )}
      {missed.length > 0 && (
        <Typography variant="caption" color="text.disabled">
          No issue found for: {missed.join(", ")}
        </Typography>
      )}
    </Stack>
  );
}

function SummaryDetail({ output }: { output: Record<string, unknown> }) {
  const narrative = output.narrative as string | undefined;
  return (
    <Stack spacing={2}>
      {narrative && (
        <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.7 }}>
          {narrative}
        </Typography>
      )}
      <Grid container spacing={2}>
        <Grid size={4}><MetricCard label="Stages" value={`${output.stages_succeeded}/${output.stages_total}`} /></Grid>
        <Grid size={4}><MetricCard label="Failed" value={output.stages_failed} highlight={(output.stages_failed as number) > 0} /></Grid>
        <Grid size={4}><MetricCard label="Duration" value={fmt(output.total_duration_ms as number)} /></Grid>
        <Grid size={4}><MetricCard label="Findings" value={output.findings_count} /></Grid>
        <Grid size={4}><MetricCard label="Actions Planned" value={output.actions_planned} /></Grid>
        <Grid size={4}><MetricCard label="Graph Updates" value={output.graph_updates_planned} /></Grid>
        {(output.stabilization_passes as number ?? 1) > 1 && (
          <Grid size={4}><MetricCard label="Act Passes" value={output.stabilization_passes} /></Grid>
        )}
        {(output.stale_issues_closed as number ?? 0) > 0 && (
          <Grid size={4}><MetricCard label="Stale Closed" value={output.stale_issues_closed} /></Grid>
        )}
      </Grid>
    </Stack>
  );
}

const DETAIL_COMPONENT: Record<string, React.ComponentType<{ output: Record<string, unknown> }>> = {
  observe:  ObserveRepoDetail,
  model:    MapModulesDetail,
  analyze:  InvestigateDetail,
  decide:   PlanDetail,
  act:      ActDetail,
  reflect:  ReflectDetail,
  persist:  LearnDetail,
  summary:  SummaryDetail,
};

// ---------------------------------------------------------------------------
// DECIDE → ACT → REFLECT stabilization loop bracket
//
// Stage IDs are suffixed with the pass number: decide_1/act_1/reflect_1,
// decide_2/act_2/reflect_2, … Each pass renders as its own LoopBracketGroup
// so the user sees the loop visually duplicate on subsequent passes.
//
//   ┌── Decide ───────────────── ┐
//   │   Act   ─────────────────  │  ⟳  1
//   │   Reflect ───────────────  ┘
//
//   ┌── Decide ───────────────── ┐
//   │   Act   ─────────────────  │  ⟳  2
//   │   Reflect ───────────────  ┘
// ---------------------------------------------------------------------------

/** True for stage IDs of the form decide_N / act_N / reflect_N */
function isLoopStage(id: string): boolean {
  return /^(decide|act|reflect)(_\d+)?$/.test(id);
}

/** Extract the pass number from a loop stage ID (e.g. "act_2" → 2) */
function loopStagePass(id: string): number {
  const m = id.match(/_(\d+)$/);
  return m ? parseInt(m[1], 10) : 1;
}

function LoopBracketGroup({
  stages,
  selectedStage,
  onStageClick,
}: {
  stages: Stage[];
  selectedStage: string | null;
  onStageClick: (id: string) => void;
}) {
  const passNum   = loopStagePass(stages[0]?.id ?? "decide_1");
  const isRunning = stages.some((s) => s.status === "running");
  const isPending = stages.every((s) => s.status === "pending");
  const isDone    = !isRunning && !isPending;

  const railColor = isRunning ? "rgba(96,165,250,0.22)"
                  : isDone    ? "rgba(96,165,250,0.35)"
                  :             "rgba(255,255,255,0.1)";
  const fgColor   = isRunning ? "rgba(96,165,250,0.75)"
                  : isDone    ? "#60a5fa"
                  :             "rgba(255,255,255,0.35)";

  return (
    // minWidth:0 + overflow:hidden prevent the flex group from stretching the 1fr grid column
    <Box sx={{ display: "flex", alignItems: "stretch", gap: "5px", minWidth: 0, overflow: "hidden" }}>
      {/* Left: stage rows, same spacing as the outer stack */}
      <Stack spacing={0.75} sx={{ flex: 1, minWidth: 0 }}>
        {stages.map((stage) => (
          <StageRow
            key={stage.id}
            stage={stage}
            selected={selectedStage === stage.id}
            onClick={() => onStageClick(stage.id)}
          />
        ))}
      </Stack>

      {/* Right: ] bracket — top + right + bottom borders, open on left */}
      <Box
        sx={{
          width: 32,
          flexShrink: 0,
          borderTop:    `1px solid ${railColor}`,
          borderRight:  `1px solid ${railColor}`,
          borderBottom: `1px solid ${railColor}`,
          borderRadius: "0 4px 4px 0",
          position: "relative",
          opacity: isPending ? 0.38 : 1,
          transition: "border-color 0.25s ease, opacity 0.25s ease",
        }}
      >
        {/* icon + pass number, vertically centred inside the bracket */}
        <Stack
          sx={{
            position: "absolute",
            top: "50%",
            left: "50%",
            transform: "translate(-50%, -50%)",
            alignItems: "center",
            gap: "3px",
          }}
        >
          <LoopIcon
            sx={{
              fontSize: 14,
              color: fgColor,
              animation: isRunning ? "loopSpin 1.4s linear infinite" : "none",
              "@keyframes loopSpin": {
                "0%":   { transform: "rotate(0deg)"   },
                "100%": { transform: "rotate(360deg)" },
              },
            }}
          />
          <Typography
            variant="caption"
            sx={{ color: fgColor, fontSize: "0.6rem", fontWeight: 700, lineHeight: 1 }}
          >
            {passNum}
          </Typography>
        </Stack>
      </Box>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Vertical stage row (replaces horizontal StageCard)
// ---------------------------------------------------------------------------
function StageRow({ stage, selected, onClick }: { stage: Stage; selected: boolean; onClick: () => void }) {
  const isRunning = stage.status === "running";
  const summary = stageSummary(stage);
  const DetailComponent = DETAIL_COMPONENT[stage.id.replace(/_\d+$/, "")];

  // A stage is expandable only if it has output to show (skipped/pending/running-without-output → not expandable)
  const isExpandable = !!stage.output && !!DetailComponent;

  const borderColor = selected
    ? stage.status === "failed" ? "error.main" : stage.status === "success" ? "success.main" : stage.status === "running" ? "primary.main" : "primary.dark"
    : stage.status === "failed" ? "error.dark" : stage.status === "success" ? "success.dark" : "divider";

  return (
    <Box>
      <Paper
        elevation={0}
        onClick={isExpandable ? onClick : undefined}
        sx={{
          px: 2,
          py: 1.25,
          cursor: isExpandable ? "pointer" : "default",
          border: "1px solid",
          borderColor,
          bgcolor: selected ? "rgba(255,255,255,0.05)" : "background.paper",
          position: "relative",
          overflow: "hidden",
          transition: "all 0.15s ease",
          "&:hover": isExpandable ? { bgcolor: "rgba(255,255,255,0.04)" } : {},
        }}
      >
        {isRunning && <LinearProgress sx={{ position: "absolute", top: 0, left: 0, right: 0, height: 2 }} />}
        <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
          <Box sx={{ color: selected ? "primary.light" : "text.secondary", display: "flex", flexShrink: 0 }}>
            {STAGE_ICONS[stage.id.replace(/_\d+$/, "")] ?? <AccessTimeIcon fontSize="small" />}
          </Box>
          <Typography variant="body2" sx={{ fontWeight: 600, minWidth: 84, flexShrink: 0 }}>
            {stage.label}
          </Typography>
          <Chip
            label={STATUS_LABEL[stage.status]}
            size="small"
            color={STATUS_COLOR[stage.status]}
            variant="outlined"
            icon={isRunning ? <LoopIcon sx={{ fontSize: "12px !important" }} /> : stage.status === "success" ? <CheckCircleOutlinedIcon sx={{ fontSize: "12px !important" }} /> : stage.status === "failed" ? <ErrorOutlinedIcon sx={{ fontSize: "12px !important" }} /> : <AccessTimeIcon sx={{ fontSize: "12px !important" }} />}
            sx={{ height: 22, fontSize: "0.65rem", flexShrink: 0 }}
          />
          {stage.error ? (
            <Typography variant="caption" color="error.main" sx={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={stage.error}>
              {stage.error}
            </Typography>
          ) : summary ? (
            <Typography variant="caption" color="text.secondary" sx={{ flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
              {summary}
            </Typography>
          ) : (
            <Box sx={{ flex: 1 }} />
          )}
          {stage.duration_ms != null && (
            <Typography variant="caption" color="text.disabled" sx={{ flexShrink: 0, fontFamily: "var(--font-google-sans-code)" }}>
              {fmt(stage.duration_ms)}
            </Typography>
          )}
          {isExpandable && (
            <ChevronRightIcon
              sx={{
                fontSize: 16,
                color: "text.disabled",
                flexShrink: 0,
                transform: selected ? "rotate(90deg)" : "none",
                transition: "transform 0.15s",
              }}
            />
          )}
        </Stack>
      </Paper>

      {/* Inline detail panel */}
      <Collapse in={selected && !!stage.output} unmountOnExit>
        {stage.output && DetailComponent && (
          <Paper
            elevation={0}
            sx={{
              p: 2.5,
              mt: 0.5,
              bgcolor: "rgba(255,255,255,0.02)",
              border: "1px solid rgba(255,255,255,0.05)",
              borderLeft: "2px solid",
              borderLeftColor: stage.status === "failed" ? "error.dark" : stage.status === "success" ? "success.dark" : "primary.dark",
            }}
          >
            <DetailComponent output={stage.output} />
          </Paper>
        )}
      </Collapse>
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function Pipeline() {
  const [run, setRun] = useState<PipelineRun | null>(null);
  const [selectedStage, setSelectedStage] = useState<string | null>(null);
  const [connected, setConnected] = useState(false);
  const [triggering, setTriggering] = useState(false);
  const [stopping, setStopping] = useState(false);
  const stoppingRunId = useRef<string | null>(null);
  const [tick, setTick] = useState(0);
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  useEffect(() => {
    const id = setInterval(() => setTick((t) => t + 1), 5000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    const es = new EventSource(`${apiUrl}/pipeline/stream`);
    es.onopen = () => setConnected(true);
    es.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data) as PipelineRun;
        setRun(data);
        // Clear stopping state when the specifically-stopped run terminates, OR when
        // a different run appears (proving the stopped run must have already ended).
        if (stoppingRunId.current !== null) {
          const stoppedRunDone = data.run_id === stoppingRunId.current && data.status !== "running";
          const newRunAppeared  = data.run_id !== stoppingRunId.current;
          if (stoppedRunDone || newRunAppeared) {
            stoppingRunId.current = null;
            setStopping(false);
          }
        }
        const running = data.stages.find((s) => s.status === "running");
        const lastStage = data.stages[data.stages.length - 1];
        if (running) {
          setSelectedStage(running.id);
        } else if (lastStage?.status === "success") {
          setSelectedStage(lastStage.id);
        }
      } catch {}
    };
    es.onerror = () => setConnected(false);
    return () => es.close();
  }, [apiUrl]);

  async function triggerRun() {
    setTriggering(true);
    try {
      await fetch(`${apiUrl}/pipeline/run`, { method: "POST" });
    } finally {
      setTriggering(false);
    }
  }

  async function stopRun() {
    if (!run) return;
    stoppingRunId.current = run.run_id;
    setStopping(true);
    try {
      await fetch(`${apiUrl}/pipeline/stop`, { method: "POST" });
    } catch {
      stoppingRunId.current = null;
      setStopping(false);
    }
  }

  return (
    <Stack spacing={2}>
      {/* Header */}
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center" }}>
        <Stack spacing={0.25}>
          <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
            <Typography variant="subtitle2" color="text.secondary">Current Run</Typography>
            {run && (
              <Chip
                label={run.status.toUpperCase()}
                size="small"
                color={run.status === "success" ? "success" : run.status === "failed" ? "error" : run.status === "running" ? "primary" : run.status === "cancelled" ? "warning" : "default"}
                variant="outlined"
                sx={{ height: 20, fontSize: "0.65rem" }}
              />
            )}
          </Stack>
          {run && (() => {
            const summaryStage = run.stages.find((s) => s.id === "summary");
            const totalMs = summaryStage?.output
              ? (summaryStage.output.total_duration_ms as number | null) ?? null
              : run.stages.reduce((a, s) => a + (s.duration_ms ?? 0), 0) || null;
            const endTs = totalMs != null ? run.started_at + totalMs / 1000 : null;
            return (
              <Typography variant="caption" color="text.disabled" sx={{ whiteSpace: "nowrap" }}>
                <Box component="span" sx={{ display: "none" }}>{tick}</Box>
                started {fmtDatetime(run.started_at)}
                {endTs != null && run.status !== "running" && (
                  <> &nbsp;→&nbsp; ended {fmtDatetime(endTs)}</>
                )}
                {totalMs != null && <> · {fmt(totalMs)}</>}
                {run.status === "running" && <> · {timeAgo(run.started_at)}</>}
              </Typography>
            );
          })()}
        </Stack>
        <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
          <Stack direction="row" spacing={0.5} sx={{ alignItems: "center" }}>
            <FiberManualRecordIcon sx={{ fontSize: 10, color: connected ? "success.main" : "text.disabled" }} />
            <Typography variant="caption" color={connected ? "success.main" : "text.disabled"}>
              {connected ? "Live" : "Disconnected"}
            </Typography>
          </Stack>
          {(run?.status === "running" || stopping) ? (
            <Button
              size="small"
              variant="outlined"
              color="error"
              onClick={stopRun}
              disabled={stopping}
              startIcon={<StopOutlinedIcon />}
              sx={{ height: 30 }}
            >
              {stopping ? "Stopping…" : "Stop"}
            </Button>
          ) : (
            <Button
              size="small"
              variant="outlined"
              onClick={triggerRun}
              disabled={triggering}
              startIcon={<PlayArrowOutlinedIcon />}
              sx={{ height: 30 }}
            >
              {triggering ? "Starting…" : "Run Now"}
            </Button>
          )}
        </Stack>
      </Stack>

      {/* Vertical stage list */}
      {!run ? (
        <Paper elevation={0} sx={{ p: 3, textAlign: "center" }}>
          <Typography variant="body2" color="text.disabled">
            {connected ? "Waiting for first pipeline run…" : "Backend unreachable"}
          </Typography>
        </Paper>
      ) : (
        <Stack spacing={0.75}>
          {/* Group consecutive DECIDE→ACT→REFLECT stages inside a ] bracket;
              render all other stages as plain rows. */}
          {(() => {
            const elements: React.ReactNode[] = [];
            let loopBuffer: Stage[] = [];

            const flushLoop = () => {
              if (loopBuffer.length === 0) return;
              const group = [...loopBuffer];
              loopBuffer = [];
              elements.push(
                <LoopBracketGroup
                  key={group.map((s) => s.id).join("|")}
                  stages={group}
                  selectedStage={selectedStage}
                  onStageClick={(id) => setSelectedStage(selectedStage === id ? null : id)}
                />
              );
            };

            for (const stage of run.stages) {
              if (isLoopStage(stage.id)) {
                // Flush if this stage belongs to a different pass than what's buffered
                if (loopBuffer.length > 0 && loopStagePass(stage.id) !== loopStagePass(loopBuffer[0].id)) {
                  flushLoop();
                }
                loopBuffer.push(stage);
              } else {
                flushLoop();
                elements.push(
                  <StageRow
                    key={stage.id}
                    stage={stage}
                    selected={selectedStage === stage.id}
                    onClick={() => setSelectedStage(selectedStage === stage.id ? null : stage.id)}
                  />
                );
              }
            }
            flushLoop();
            return elements;
          })()}
        </Stack>
      )}
    </Stack>
  );
}
