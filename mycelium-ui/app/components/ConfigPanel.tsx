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

import CheckCircleOutlinedIcon from "@mui/icons-material/CheckCircleOutlined";
import CloudOutlinedIcon from "@mui/icons-material/CloudOutlined";
import CodeOutlinedIcon from "@mui/icons-material/CodeOutlined";
import ErrorOutlinedIcon from "@mui/icons-material/ErrorOutlined";
import HubOutlinedIcon from "@mui/icons-material/HubOutlined";
import PauseCircleOutlinedIcon from "@mui/icons-material/PauseCircleOutlined";
import PlayCircleOutlinedIcon from "@mui/icons-material/PlayCircleOutlined";
import RefreshIcon from "@mui/icons-material/Refresh";
import ScienceOutlinedIcon from "@mui/icons-material/ScienceOutlined";
import StorageOutlinedIcon from "@mui/icons-material/StorageOutlined";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
type Config = {
  google_cloud_project: string;
  google_cloud_location: string;
  gemini_model: string;
  gitlab_url: string;
  gitlab_project_id: number;
  mongodb_db: string;
  pipeline_loop_enabled: boolean;
  agent_loop_interval_seconds: number;
  demo_mode: boolean;
};

// ---------------------------------------------------------------------------
// Row — a single key/value config line
// ---------------------------------------------------------------------------
function Row({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <Stack
      direction="row"
      sx={{ alignItems: "center", justifyContent: "space-between", py: 1.25, px: 0 }}
    >
      <Typography variant="body2" color="text.secondary" sx={{ minWidth: 200 }}>
        {label}
      </Typography>
      {typeof value === "string" ? (
        <Typography
          variant="body2"
          color="text.primary"
          sx={{
            fontFamily: mono ? "var(--font-google-sans-code)" : undefined,
            textAlign: "right",
          }}
        >
          {value}
        </Typography>
      ) : (
        value
      )}
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Section — card with a header
// ---------------------------------------------------------------------------
function Section({
  icon,
  title,
  children,
}: {
  icon: React.ReactNode;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Paper sx={{ overflow: "hidden" }}>
      <Stack
        direction="row"
        sx={{ alignItems: "center", px: 2.5, py: 1.5, bgcolor: "rgba(255,255,255,0.03)" }}
        spacing={1}
      >
        <Box sx={{ color: "text.secondary", display: "flex" }}>{icon}</Box>
        <Typography variant="subtitle2" sx={{ fontWeight: 600 }} color="text.primary">
          {title}
        </Typography>
      </Stack>
      <Divider sx={{ borderColor: "rgba(255,255,255,0.06)" }} />
      <Box sx={{ px: 2.5 }}>
        {children}
      </Box>
    </Paper>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function ConfigPanel() {
  const [cfg, setCfg] = useState<Config | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  const fetchConfig = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiUrl}/config`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setCfg(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fetch failed");
    } finally {
      setLoading(false);
    }
  }, [apiUrl]);

  useEffect(() => { fetchConfig(); }, [fetchConfig]);

  if (loading && !cfg) {
    return (
      <Stack direction="row" sx={{ alignItems: "center", color: "text.secondary", py: 4 }} spacing={1.5}>
        <CircularProgress size={18} />
        <Typography variant="body2" color="text.secondary">Loading configuration…</Typography>
      </Stack>
    );
  }

  if (error && !cfg) {
    return (
      <Stack direction="row" sx={{ alignItems: "center", color: "error.main", py: 4 }} spacing={1}>
        <ErrorOutlinedIcon fontSize="small" />
        <Typography variant="body2">{error}</Typography>
      </Stack>
    );
  }

  return (
    <Stack spacing={2.5}>
      {/* Toolbar */}
      <Stack direction="row" sx={{ alignItems: "center", justifyContent: "space-between" }}>
        <Stack direction="row" sx={{ alignItems: "center" }} spacing={1}>
          {cfg && (
            <Chip
              icon={<CheckCircleOutlinedIcon sx={{ fontSize: "14px !important" }} />}
              label="Connected to backend"
              size="small"
              color="success"
              variant="outlined"
              sx={{ height: 22, fontSize: "0.7rem" }}
            />
          )}
          {loading && <CircularProgress size={14} />}
        </Stack>
        <IconButton size="small" onClick={fetchConfig} disabled={loading} sx={{ color: "text.secondary" }}>
          <RefreshIcon fontSize="small" />
        </IconButton>
      </Stack>

      {cfg && (
        <>
          {/* Google Cloud */}
          <Section icon={<CloudOutlinedIcon fontSize="small" />} title="Google Cloud / Vertex AI">
            <Row label="Project" value={cfg.google_cloud_project} mono />
            <Divider sx={{ borderColor: "rgba(255,255,255,0.04)" }} />
            <Row label="Location" value={cfg.google_cloud_location} mono />
            <Divider sx={{ borderColor: "rgba(255,255,255,0.04)" }} />
            <Row
              label="Model"
              value={
                <Chip
                  label={cfg.gemini_model}
                  size="small"
                  variant="outlined"
                  sx={{ height: 22, fontSize: "0.7rem", color: "primary.light", borderColor: "primary.dark", fontFamily: "var(--font-google-sans-code)" }}
                />
              }
            />
          </Section>

          {/* GitLab */}
          <Section icon={<CodeOutlinedIcon fontSize="small" />} title="GitLab">
            <Row label="Instance" value={cfg.gitlab_url} mono />
            <Divider sx={{ borderColor: "rgba(255,255,255,0.04)" }} />
            <Row label="Project ID" value={String(cfg.gitlab_project_id)} mono />
          </Section>

          {/* MongoDB */}
          <Section icon={<StorageOutlinedIcon fontSize="small" />} title="MongoDB">
            <Row label="Database" value={cfg.mongodb_db} mono />
          </Section>

          {/* Demo mode */}
          <Section icon={<ScienceOutlinedIcon fontSize="small" />} title="Demo Mode">
            <Row
              label="DEMO_MODE"
              value={
                <Chip
                  icon={<ScienceOutlinedIcon sx={{ fontSize: "14px !important" }} />}
                  label={cfg.demo_mode ? "Enabled" : "Disabled"}
                  size="small"
                  color={cfg.demo_mode ? "secondary" : "default"}
                  variant="outlined"
                  sx={{ height: 22, fontSize: "0.7rem", ...(cfg.demo_mode && { color: "#a78bfa", borderColor: "#7c3aed" }) }}
                />
              }
            />
            <Box sx={{ py: 1.25 }}>
              <Typography variant="caption" color="text.disabled">
                {cfg.demo_mode
                  ? "Demo data is visible to pipeline agents. Seeded contributors appear in generated findings and issues."
                  : "Demo data is excluded from pipeline agents. Set DEMO_MODE=true in .env to include seeded team data in agent context."}
              </Typography>
            </Box>
          </Section>

          {/* Pipeline loop */}
          <Section icon={<HubOutlinedIcon fontSize="small" />} title="Pipeline Loop">
            <Row
              label="Auto-loop"
              value={
                <Chip
                  icon={
                    cfg.pipeline_loop_enabled
                      ? <PlayCircleOutlinedIcon sx={{ fontSize: "14px !important" }} />
                      : <PauseCircleOutlinedIcon sx={{ fontSize: "14px !important" }} />
                  }
                  label={cfg.pipeline_loop_enabled ? "Enabled" : "Disabled"}
                  size="small"
                  color={cfg.pipeline_loop_enabled ? "success" : "default"}
                  variant="outlined"
                  sx={{ height: 22, fontSize: "0.7rem" }}
                />
              }
            />
            <Divider sx={{ borderColor: "rgba(255,255,255,0.04)" }} />
            <Row
              label="Interval"
              value={
                <Typography variant="body2" color={cfg.pipeline_loop_enabled ? "text.primary" : "text.disabled"} sx={{ fontFamily: "var(--font-google-sans-code)" }}>
                  {cfg.agent_loop_interval_seconds}s
                  {cfg.agent_loop_interval_seconds >= 60
                    ? ` (${Math.round(cfg.agent_loop_interval_seconds / 60)}m)`
                    : ""}
                </Typography>
              }
            />
            {!cfg.pipeline_loop_enabled && (
              <Box sx={{ py: 1.25 }}>
                <Typography variant="caption" color="text.disabled">
                  Auto-loop is off. Trigger runs manually via{" "}
                  <Box component="span" sx={{ fontFamily: "var(--font-google-sans-code)", color: "text.secondary" }}>
                    POST /pipeline/run
                  </Box>{" "}
                  or the Run button on the Pipeline page.
                </Typography>
              </Box>
            )}
          </Section>
        </>
      )}
    </Stack>
  );
}
