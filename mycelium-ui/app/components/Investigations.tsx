"use client";

import { useCallback, useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import BiotechOutlinedIcon from "@mui/icons-material/BiotechOutlined";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import PersonOutlinedIcon from "@mui/icons-material/PersonOutlined";
import RefreshIcon from "@mui/icons-material/Refresh";
import SyncProblemOutlinedIcon from "@mui/icons-material/SyncProblemOutlined";

import Md from "./Md";

// ---------------------------------------------------------------------------
// Types — match the investigate stage output in agent/pipeline.py
// ---------------------------------------------------------------------------
type MemberInvestigation = {
  member: string;
  attention_reason: string;
  uniquely_owned_modules: string[];
  knowledge_at_risk?: string;
  transferability_today?: string;
  urgency_reasoning?: string;
  recommended_actions?: string[];
  documentation_gaps?: string[];
};

type ModuleInvestigation = {
  module: string;
  investigated: boolean;
  files_read_count?: number;
  transferability_assessment?: string;
  doc_coverage?: number;
  documentation_state?: string;
  key_concerns?: string[];
  knowledge_at_risk_if_top_contributor_leaves?: string;
  recommended_documentation_actions?: string[];
  severity_reasoning?: string;
  reason?: string;
};

type DriftInvestigation = {
  investigated: boolean;
  commits_behind?: number;
  upstream_project?: string;
  urgency_assessment?: string;
  high_priority_commits?: { id: string; title: string; why: string }[];
  low_priority_dominance?: boolean;
  recommended_action?: string;
  severity_reasoning?: string;
  reason?: string;
};

type StageOutput = {
  high_attention_members?: number;
  member_investigations?: number;
  module_investigations?: number;
  drift_investigated?: boolean;
  members?: MemberInvestigation[];
  modules?: ModuleInvestigation[];
  drift?: DriftInvestigation | null;
};

type Stage = { id: string; label: string; status: string; output?: StageOutput | null };
type Run = { run_id: string; status: string; stages: Stage[] };

// ---------------------------------------------------------------------------
// Display helpers
// ---------------------------------------------------------------------------
const REASON_COLORS: Record<string, string> = {
  sole_contributor: "#ea4335",
  multi_module_concentration: "#fa7b17",
  recently_inactive: "#fbbc04",
  recent_joiner: "#4285f4",
};

const DOC_STATE_COLORS: Record<string, string> = {
  excellent: "#34a853",
  adequate: "#8ab4f8",
  sparse: "#fbbc04",
  placeholder: "#fa7b17",
  missing: "#ea4335",
};

function reasonColor(r: string): string {
  return REASON_COLORS[r] ?? "#8ab4f8";
}

function docStateColor(s: string | undefined): string {
  return DOC_STATE_COLORS[s ?? ""] ?? "#8ab4f8";
}

// ---------------------------------------------------------------------------
// Card primitives
// ---------------------------------------------------------------------------
function FindingCard({
  icon, title, headerChip, children,
}: {
  icon: React.ReactNode;
  title: string;
  headerChip?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <Paper
      elevation={0}
      sx={{
        overflow: "hidden",
        border: "1px solid rgba(255,255,255,0.08)",
        borderRadius: 2,
        bgcolor: "background.paper",
      }}
    >
      <Stack
        direction="row"
        sx={{ alignItems: "center", px: 2.5, py: 1.5, bgcolor: "rgba(255,255,255,0.02)" }}
        spacing={1.5}
      >
        {icon}
        <Typography variant="subtitle2" sx={{ fontWeight: 600, color: "text.primary", flex: 1 }}>
          {title}
        </Typography>
        {headerChip}
      </Stack>
      <Divider sx={{ borderColor: "rgba(255,255,255,0.06)" }} />
      <Box sx={{ px: 2.5, py: 2 }}>{children}</Box>
    </Paper>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Box sx={{ mb: 1.5 }}>
      <Typography
        variant="caption"
        sx={{
          display: "block",
          textTransform: "uppercase",
          letterSpacing: "0.08em",
          fontSize: "0.65rem",
          color: "text.secondary",
          mb: 0.5,
        }}
      >
        {label}
      </Typography>
      {/* component="div" prevents <p> wrapping block children like <ul> */}
      <Typography component="div" variant="body2" sx={{ color: "text.secondary", lineHeight: 1.6 }}>
        {children}
      </Typography>
    </Box>
  );
}

function BulletList({ items }: { items: string[] | undefined }) {
  if (!items || items.length === 0) return null;
  return (
    <Box component="ul" sx={{ pl: 2.5, my: 0, color: "text.secondary" }}>
      {items.map((it, i) => (
        <Box component="li" key={i} sx={{ fontSize: "0.85rem", lineHeight: 1.6,
          "& p": { m: 0, display: "inline" },
          "& strong": { fontWeight: 600, color: "text.primary" },
          "& code": { fontFamily: "var(--font-google-sans-code)", fontSize: "0.85em", bgcolor: "rgba(255,255,255,0.07)", px: 0.5, borderRadius: 0.5 },
        }}>
          <Md>{it}</Md>
        </Box>
      ))}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Per-investigation cards
// ---------------------------------------------------------------------------
function MemberCard({ m }: { m: MemberInvestigation }) {
  return (
    <FindingCard
      icon={<PersonOutlinedIcon sx={{ fontSize: 18, color: reasonColor(m.attention_reason) }} />}
      title={m.member}
      headerChip={
        <Chip
          label={m.attention_reason.replace(/_/g, " ")}
          size="small"
          variant="outlined"
          sx={{
            height: 20,
            fontSize: "0.65rem",
            color: reasonColor(m.attention_reason),
            borderColor: reasonColor(m.attention_reason) + "55",
          }}
        />
      }
    >
      {m.uniquely_owned_modules?.length > 0 && (
        <Field label="Uniquely owned modules">
          <Stack direction="row" spacing={0.5} sx={{ flexWrap: "wrap", gap: 0.5 }}>
            {m.uniquely_owned_modules.map((mod) => (
              <Chip key={mod} label={mod} size="small" variant="outlined"
                sx={{ height: 18, fontSize: "0.6rem", fontFamily: "var(--font-google-sans-code)" }} />
            ))}
          </Stack>
        </Field>
      )}
      {m.knowledge_at_risk && <Field label="Knowledge at risk"><Md>{m.knowledge_at_risk}</Md></Field>}
      {m.transferability_today && <Field label="Transferability today"><Md>{m.transferability_today}</Md></Field>}
      {m.urgency_reasoning && <Field label="Urgency reasoning"><Md>{m.urgency_reasoning}</Md></Field>}
      {m.recommended_actions && m.recommended_actions.length > 0 && (
        <Field label="Recommended actions"><BulletList items={m.recommended_actions} /></Field>
      )}
      {m.documentation_gaps && m.documentation_gaps.length > 0 && (
        <Field label="Documentation gaps"><BulletList items={m.documentation_gaps} /></Field>
      )}
    </FindingCard>
  );
}

function ModuleCard({ m }: { m: ModuleInvestigation }) {
  if (!m.investigated) {
    return (
      <FindingCard
        icon={<FolderOutlinedIcon sx={{ fontSize: 18, color: "text.disabled" }} />}
        title={m.module}
        headerChip={<Chip label="not investigated" size="small" variant="outlined"
          sx={{ height: 20, fontSize: "0.65rem", color: "text.disabled" }} />}
      >
        <Typography variant="body2" color="text.disabled">{m.reason ?? "No content available."}</Typography>
      </FindingCard>
    );
  }
  return (
    <FindingCard
      icon={<FolderOutlinedIcon sx={{ fontSize: 18, color: docStateColor(m.documentation_state) }} />}
      title={m.module}
      headerChip={
        <Stack direction="row" spacing={0.5}>
          {m.files_read_count !== undefined && (
            <Chip label={`${m.files_read_count} files`} size="small" variant="outlined"
              sx={{ height: 20, fontSize: "0.65rem", color: "text.disabled" }} />
          )}
          {m.documentation_state && (
            <Chip label={m.documentation_state} size="small" variant="outlined"
              sx={{ height: 20, fontSize: "0.65rem", color: docStateColor(m.documentation_state),
                    borderColor: docStateColor(m.documentation_state) + "55" }} />
          )}
        </Stack>
      }
    >
      {m.transferability_assessment && <Field label="Transferability"><Md>{m.transferability_assessment}</Md></Field>}
      {m.knowledge_at_risk_if_top_contributor_leaves && (
        <Field label="Knowledge at risk if top contributor leaves">
          <Md>{m.knowledge_at_risk_if_top_contributor_leaves}</Md>
        </Field>
      )}
      {m.severity_reasoning && <Field label="Severity reasoning"><Md>{m.severity_reasoning}</Md></Field>}
      {m.key_concerns && m.key_concerns.length > 0 && (
        <Field label="Key concerns"><BulletList items={m.key_concerns} /></Field>
      )}
      {m.recommended_documentation_actions && m.recommended_documentation_actions.length > 0 && (
        <Field label="Recommended documentation actions">
          <BulletList items={m.recommended_documentation_actions} />
        </Field>
      )}
    </FindingCard>
  );
}

function DriftCard({ d }: { d: DriftInvestigation }) {
  if (!d.investigated) {
    return (
      <FindingCard
        icon={<SyncProblemOutlinedIcon sx={{ fontSize: 18, color: "text.disabled" }} />}
        title="Upstream drift"
        headerChip={<Chip label="not investigated" size="small" variant="outlined"
          sx={{ height: 20, fontSize: "0.65rem", color: "text.disabled" }} />}
      >
        <Typography variant="body2" color="text.disabled">{d.reason ?? "Not a fork or no divergence."}</Typography>
      </FindingCard>
    );
  }
  return (
    <FindingCard
      icon={<SyncProblemOutlinedIcon sx={{ fontSize: 18, color: "#fbbc04" }} />}
      title={`Upstream drift — ${d.upstream_project ?? "unknown"}`}
      headerChip={
        <Chip label={`${d.commits_behind ?? 0} commits behind`} size="small" variant="outlined"
          sx={{ height: 20, fontSize: "0.65rem", color: "#fbbc04", borderColor: "#fbbc0455" }} />
      }
    >
      {d.urgency_assessment && <Field label="Urgency (content-driven)"><Md>{d.urgency_assessment}</Md></Field>}
      {d.severity_reasoning && <Field label="Severity reasoning"><Md>{d.severity_reasoning}</Md></Field>}
      {d.high_priority_commits && d.high_priority_commits.length > 0 && (
        <Field label="High-priority commits">
          <Box component="ul" sx={{ pl: 2.5, my: 0, color: "text.secondary" }}>
            {d.high_priority_commits.map((c, i) => (
              <Box component="li" key={i} sx={{ fontSize: "0.85rem", lineHeight: 1.6, mb: 0.75 }}>
                <Box component="span" sx={{ fontFamily: "var(--font-google-sans-code)", color: "primary.light" }}>
                  {c.id}
                </Box>{" — "}{c.title}
                <Box sx={{ pl: 1, color: "text.disabled", fontStyle: "italic" }}>{c.why}</Box>
              </Box>
            ))}
          </Box>
        </Field>
      )}
      {d.recommended_action && <Field label="Recommended action"><Md>{d.recommended_action}</Md></Field>}
    </FindingCard>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function Investigations() {
  const [data, setData] = useState<StageOutput | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      // Try current run first, fall back to last history entry
      let res = await fetch(`${apiUrl}/pipeline/current`);
      if (res.ok) {
        const body = await res.json();
        const run: Run | null = body.run;
        if (run) {
          const stage = run.stages.find((s) => s.id === "investigate");
          if (stage?.output) {
            setData(stage.output);
            setLoading(false);
            return;
          }
        }
      }
      res = await fetch(`${apiUrl}/pipeline/history`);
      if (res.ok) {
        const body = await res.json();
        const runs: Run[] = body.runs || [];
        for (let i = runs.length - 1; i >= 0; i--) {
          const stage = runs[i].stages.find((s) => s.id === "investigate");
          if (stage?.output) {
            setData(stage.output);
            setLoading(false);
            return;
          }
        }
      }
      setData(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fetch failed");
    } finally {
      setLoading(false);
    }
  }, [apiUrl]);

  useEffect(() => { fetchData(); }, [fetchData]);

  const members = data?.members ?? [];
  const modules = data?.modules ?? [];
  const drift = data?.drift ?? null;
  const empty = !loading && members.length === 0 && modules.length === 0 && !drift;

  return (
    <Stack spacing={3}>
      {/* Toolbar */}
      <Stack direction="row" sx={{ alignItems: "center", justifyContent: "space-between" }}>
        <Stack direction="row" spacing={2} sx={{ alignItems: "center" }}>
          {data && (
            <Typography variant="caption" color="text.disabled">
              {data.member_investigations ?? 0} member · {data.module_investigations ?? 0} module
              {drift && drift.investigated ? " · 1 drift" : ""} investigation
              {(data.member_investigations ?? 0) + (data.module_investigations ?? 0) !== 1 ? "s" : ""}
            </Typography>
          )}
          {loading && <CircularProgress size={14} />}
        </Stack>
        <Button size="small" variant="outlined" onClick={fetchData} disabled={loading}
          startIcon={<RefreshIcon />} sx={{ height: 30 }}>
          {loading ? "Loading…" : "Refresh"}
        </Button>
      </Stack>

      {error && <Typography variant="body2" color="error.main">{error}</Typography>}

      {empty && (
        <Paper elevation={0} sx={{ p: 4, textAlign: "center" }}>
          <BiotechOutlinedIcon sx={{ fontSize: 32, color: "text.disabled", mb: 1 }} />
          <Typography variant="body2" color="text.disabled">
            No investigations yet — run the pipeline to spawn investigator subagents.
          </Typography>
        </Paper>
      )}

      {/* Members section */}
      {members.length > 0 && (
        <Box>
          <Typography variant="subtitle2" sx={{ mb: 1.5, fontWeight: 600, color: "text.primary" }}>
            High-attention members ({members.length})
          </Typography>
          <Stack spacing={1.5}>
            {members.map((m, i) => <MemberCard key={`${m.member}-${i}`} m={m} />)}
          </Stack>
        </Box>
      )}

      {/* Modules section */}
      {modules.length > 0 && (
        <Box>
          <Typography variant="subtitle2" sx={{ mb: 1.5, fontWeight: 600, color: "text.primary" }}>
            Module investigations ({modules.length})
          </Typography>
          <Stack spacing={1.5}>
            {modules.map((m, i) => <ModuleCard key={`${m.module}-${i}`} m={m} />)}
          </Stack>
        </Box>
      )}

      {/* Drift section */}
      {drift && (
        <Box>
          <Typography variant="subtitle2" sx={{ mb: 1.5, fontWeight: 600, color: "text.primary" }}>
            Upstream drift
          </Typography>
          <DriftCard d={drift} />
        </Box>
      )}
    </Stack>
  );
}
