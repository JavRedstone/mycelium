"use client";

import { useEffect, useState } from "react";
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
import SchoolOutlinedIcon from "@mui/icons-material/SchoolOutlined";
import AssessmentOutlinedIcon from "@mui/icons-material/AssessmentOutlined";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";
import FiberManualRecordIcon from "@mui/icons-material/FiberManualRecord";
import LoopIcon from "@mui/icons-material/Loop";
import CheckCircleOutlinedIcon from "@mui/icons-material/CheckCircleOutlined";
import ErrorOutlinedIcon from "@mui/icons-material/ErrorOutlined";
import AccessTimeIcon from "@mui/icons-material/AccessTime";
import ExtensionOutlinedIcon from "@mui/icons-material/ExtensionOutlined";
import FolderOpenOutlinedIcon from "@mui/icons-material/FolderOpenOutlined";
import BiotechOutlinedIcon from "@mui/icons-material/BiotechOutlined";
import Md from "./Md";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
type StageStatus = "pending" | "running" | "success" | "failed" | "skipped";

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
  return `${Math.floor(diff / 3600)}h ago`;
}

const STATUS_COLOR: Record<StageStatus, "default" | "primary" | "success" | "error"> = {
  pending: "default",
  running: "primary",
  success: "success",
  failed: "error",
  skipped: "default",
};

const STATUS_LABEL: Record<StageStatus, string> = {
  pending: "Pending",
  running: "Running",
  success: "Done",
  failed: "Failed",
  skipped: "Skipped",
};

export const STAGE_ICONS: Record<string, React.ReactElement> = {
  observe_repo: <VisibilityOutlinedIcon fontSize="small" />,
  map_modules: <FolderOpenOutlinedIcon fontSize="small" />,
  investigate: <BiotechOutlinedIcon fontSize="small" />,
  observe_graph: <AccountTreeOutlinedIcon fontSize="small" />,
  interpret: <BoltOutlinedIcon fontSize="small" />,
  plan: <AssignmentOutlinedIcon fontSize="small" />,
  act: <PlayArrowOutlinedIcon fontSize="small" />,
  learn: <SchoolOutlinedIcon fontSize="small" />,
  summary: <AssessmentOutlinedIcon fontSize="small" />,
};

// ---------------------------------------------------------------------------
// Inline stage summary (single line, key metrics)
// ---------------------------------------------------------------------------
function stageSummary(stage: Stage): string | null {
  if (!stage.output) return stage.description ?? null;
  const o = stage.output;
  switch (stage.id) {
    case "observe_repo":
      return `${o.commit_contributors ?? 0} contributors · ${o.upstream_authors ?? 0} upstream`;
    case "map_modules":
      return `${o.modules_discovered ?? 0} modules · ${o.total_attributions ?? 0} author attributions`;
    case "investigate":
      return `${o.member_investigations ?? 0} member · ${o.module_investigations ?? 0} module · ${o.drift_investigated ? "1 drift" : "no drift"}`;
    case "observe_graph":
      return `${o.developers_tracked ?? 0} devs · ${o.upstream_authors_tracked ?? 0} upstream · ${o.concentrated_modules ?? 0} concentrated`;
    case "interpret":
      return `${o.finding_count ?? 0} findings · ${(o.concern_types as string[])?.length ?? 0} concern types`;
    case "plan":
      return `${o.actions_planned ?? 0} actions · ${o.graph_updates_planned ?? 0} graph updates`;
    case "act":
      return `${o.executed ?? 0} executed · ${o.failed ?? 0} failed · ${(o.mcp_calls as unknown[])?.length ?? 0} MCP calls`;
    case "learn":
      return `${o.updated ?? 0}/${o.total ?? 0} records · ${o.findings_saved ?? 0} findings saved`;
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
        {String(value ?? "—")}
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
    return (
      <Stack spacing={1.5}>
        <Grid container spacing={2}>
          <Grid size={4}><MetricCard label="Member Investigations" value={0} /></Grid>
          <Grid size={4}><MetricCard label="Module Investigations" value={moduleCount} /></Grid>
          <Grid size={4}><MetricCard label="Drift" value={driftInvestigated ? "Yes" : "No"} /></Grid>
        </Grid>
        <Typography variant="body2" color="text.disabled">
          No high-attention members detected this run — no member investigators were spawned.
          Module investigators ran for each discovered code directory.
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

function ObserveGraphDetail({ output }: { output: Record<string, unknown> }) {
  const upstreamTracked = (output.upstream_authors_tracked as number) ?? 0;
  return (
    <Grid container spacing={2}>
      <Grid size={3}><MetricCard label="Developers Tracked" value={output.developers_tracked} /></Grid>
      <Grid size={3}><MetricCard label="Upstream Authors" value={upstreamTracked} highlight={upstreamTracked > 0} /></Grid>
      <Grid size={3}><MetricCard label="Concentrated Modules" value={output.concentrated_modules} /></Grid>
      <Grid size={3}><MetricCard label="Recent Findings" value={output.recent_findings} /></Grid>
    </Grid>
  );
}

function InterpretDetail({ output }: { output: Record<string, unknown> }) {
  const findings = (output.findings as Array<Record<string, unknown>>) ?? [];
  return (
    <Stack spacing={2}>
      <Box sx={{ color: "text.secondary" }}>
        <Md>{String(output.synthesis ?? "")}</Md>
      </Box>
      {findings.length > 0 ? (
        <Stack spacing={1}>
          {findings.map((f, i) => {
            const actions = (f.recommended_actions as string[]) ?? [];
            const evidence = (f.evidence as string[]) ?? [];
            return (
              <Paper key={i} elevation={0} sx={{ p: 1.5, bgcolor: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 1.5 }}>
                <Stack spacing={1}>
                  <Stack direction="row" spacing={1} sx={{ alignItems: "center", flexWrap: "wrap" }}>
                    <Chip
                      label={String(f.concern_type ?? "concern").replace(/_/g, " ")}
                      size="small"
                      variant="outlined"
                      sx={{ height: 22, fontSize: "0.7rem" }}
                    />
                    <Typography variant="body2" sx={{ fontFamily: "var(--font-google-sans-code)", fontWeight: 600 }}>
                      {String(f.subject ?? "")}
                    </Typography>
                  </Stack>
                  <Md>{String(f.narrative ?? "")}</Md>
                  {actions.length > 0 && (
                    <Box>
                      <Typography variant="caption" color="text.disabled" sx={{ display: "block", mb: 0.5, textTransform: "uppercase", letterSpacing: "0.08em", fontSize: "0.6rem" }}>
                        Recommended actions
                      </Typography>
                      <Box component="ul" sx={{ pl: 2.5, my: 0, color: "text.secondary" }}>
                        {actions.map((a, j) => (
                          <Box component="li" key={j} sx={{ fontSize: "0.8rem", lineHeight: 1.5 }}>{a}</Box>
                        ))}
                      </Box>
                    </Box>
                  )}
                  {evidence.length > 0 && (
                    <Stack direction="row" spacing={0.5} sx={{ flexWrap: "wrap" }} useFlexGap>
                      {evidence.map((e, j) => (
                        <Chip key={j} label={e} size="small" variant="outlined" sx={{ height: 18, fontSize: "0.6rem", fontFamily: "var(--font-google-sans-code)", color: "text.disabled" }} />
                      ))}
                    </Stack>
                  )}
                </Stack>
              </Paper>
            );
          })}
        </Stack>
      ) : (
        <Typography variant="body2" color="text.disabled">No findings produced</Typography>
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
  const mcpCalls = (output.mcp_calls as Array<Record<string, unknown>>) ?? [];
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
      {mcpCalls.length > 0 && (
        <Box>
          <Stack direction="row" spacing={0.75} sx={{ alignItems: "center", mb: 1 }}>
            <ExtensionOutlinedIcon sx={{ fontSize: 14, color: "text.disabled" }} />
            <Typography variant="caption" color="text.disabled">MCP tool calls</Typography>
          </Stack>
          <Stack direction="row" spacing={0.75} sx={{ flexWrap: "wrap" }} useFlexGap>
            {mcpCalls.map((tc, i) => (
              <Chip key={i} label={String(tc.tool ?? "")} size="small" variant="outlined" sx={{ fontFamily: "var(--font-google-sans-code)", height: 22, fontSize: "0.7rem", color: "primary.light", borderColor: "primary.dark" }} />
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

function SummaryDetail({ output }: { output: Record<string, unknown> }) {
  return (
    <Grid container spacing={2}>
      <Grid size={4}><MetricCard label="Stages" value={`${output.stages_succeeded}/${output.stages_total}`} /></Grid>
      <Grid size={4}><MetricCard label="Failed" value={output.stages_failed} highlight={(output.stages_failed as number) > 0} /></Grid>
      <Grid size={4}><MetricCard label="Duration" value={fmt(output.total_duration_ms as number)} /></Grid>
      <Grid size={4}><MetricCard label="Findings" value={output.findings_count} /></Grid>
      <Grid size={4}><MetricCard label="Actions Planned" value={output.actions_planned} /></Grid>
      <Grid size={4}><MetricCard label="Graph Updates" value={output.graph_updates_planned} /></Grid>
    </Grid>
  );
}

const DETAIL_COMPONENT: Record<string, React.ComponentType<{ output: Record<string, unknown> }>> = {
  observe_repo: ObserveRepoDetail,
  map_modules: MapModulesDetail,
  investigate: InvestigateDetail,
  observe_graph: ObserveGraphDetail,
  interpret: InterpretDetail,
  plan: PlanDetail,
  act: ActDetail,
  learn: LearnDetail,
  summary: SummaryDetail,
};

// ---------------------------------------------------------------------------
// Vertical stage row (replaces horizontal StageCard)
// ---------------------------------------------------------------------------
function StageRow({ stage, selected, onClick }: { stage: Stage; selected: boolean; onClick: () => void }) {
  const isRunning = stage.status === "running";
  const summary = stageSummary(stage);
  const DetailComponent = DETAIL_COMPONENT[stage.id];

  const borderColor = selected
    ? stage.status === "failed" ? "error.main" : stage.status === "success" ? "success.main" : stage.status === "running" ? "primary.main" : "primary.dark"
    : stage.status === "failed" ? "error.dark" : stage.status === "success" ? "success.dark" : "divider";

  return (
    <Box>
      <Paper
        elevation={0}
        onClick={onClick}
        sx={{
          px: 2,
          py: 1.25,
          cursor: "pointer",
          border: "1px solid",
          borderColor,
          bgcolor: selected ? "rgba(255,255,255,0.05)" : "background.paper",
          position: "relative",
          overflow: "hidden",
          transition: "all 0.15s ease",
          "&:hover": { bgcolor: "rgba(255,255,255,0.04)" },
        }}
      >
        {isRunning && <LinearProgress sx={{ position: "absolute", top: 0, left: 0, right: 0, height: 2 }} />}
        <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
          <Box sx={{ color: selected ? "primary.light" : "text.secondary", display: "flex", flexShrink: 0 }}>
            {STAGE_ICONS[stage.id] ?? <AccessTimeIcon fontSize="small" />}
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
          <ChevronRightIcon
            sx={{
              fontSize: 16,
              color: "text.disabled",
              flexShrink: 0,
              transform: selected ? "rotate(90deg)" : "none",
              transition: "transform 0.15s",
            }}
          />
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
        const running = data.stages.find((s) => s.status === "running");
        if (running) {
          setSelectedStage(running.id);
        } else {
          setSelectedStage((prev) => {
            if (prev) return prev;
            const done = [...data.stages].reverse().find((s) => s.status === "success");
            return done?.id ?? null;
          });
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

  return (
    <Stack spacing={2}>
      {/* Header */}
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center" }}>
        <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
          <Typography variant="subtitle2" color="text.secondary">Current Run</Typography>
          {run && (
            <Typography variant="caption" color="text.disabled">
              started {timeAgo(run.started_at)}
              <Box component="span" sx={{ display: "none" }}>{tick}</Box>
            </Typography>
          )}
          {run && (
            <Chip
              label={run.status.toUpperCase()}
              size="small"
              color={run.status === "success" ? "success" : run.status === "failed" ? "error" : run.status === "running" ? "primary" : "default"}
              variant="outlined"
              sx={{ height: 20, fontSize: "0.65rem" }}
            />
          )}
        </Stack>
        <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
          <Stack direction="row" spacing={0.5} sx={{ alignItems: "center" }}>
            <FiberManualRecordIcon sx={{ fontSize: 10, color: connected ? "success.main" : "text.disabled" }} />
            <Typography variant="caption" color={connected ? "success.main" : "text.disabled"}>
              {connected ? "Live" : "Disconnected"}
            </Typography>
          </Stack>
          <Button
            size="small"
            variant="outlined"
            onClick={triggerRun}
            disabled={triggering || run?.status === "running"}
            startIcon={<PlayArrowOutlinedIcon />}
            sx={{ height: 30 }}
          >
            {triggering ? "Starting…" : run?.status === "running" ? "Running…" : "Run Now"}
          </Button>
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
          {run.stages.map((stage) => (
            <StageRow
              key={stage.id}
              stage={stage}
              selected={selectedStage === stage.id}
              onClick={() => setSelectedStage(selectedStage === stage.id ? null : stage.id)}
            />
          ))}
        </Stack>
      )}
    </Stack>
  );
}
