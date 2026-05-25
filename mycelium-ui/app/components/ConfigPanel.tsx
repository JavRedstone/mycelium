"use client";

import { useCallback, useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import TextField from "@mui/material/TextField";
import Typography from "@mui/material/Typography";

import Menu from "@mui/material/Menu";
import MenuItem from "@mui/material/MenuItem";

import CheckCircleOutlinedIcon from "@mui/icons-material/CheckCircleOutlined";
import CloudOutlinedIcon from "@mui/icons-material/CloudOutlined";
import CodeOutlinedIcon from "@mui/icons-material/CodeOutlined";
import DeleteOutlinedIcon from "@mui/icons-material/DeleteOutlined";
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
  demo_mode: boolean;
  // runtime config - editable via PATCH /config
  loop_enabled: boolean;
  loop_interval_seconds: number;
  analyst_max_investigators: number;
};

// ---------------------------------------------------------------------------
// Row - a single key/value config line
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
// Section - card with a header
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
type BotIssueResult = { closed: number; errors: number; total: number };

export default function ConfigPanel() {
  const [cfg, setCfg] = useState<Config | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Loop runtime config editing
  const [loopIntervalInput, setLoopIntervalInput] = useState("");
  const [maxInvestigatorsInput, setMaxInvestigatorsInput] = useState("");
  const [loopSaving, setLoopSaving] = useState(false);
  const [loopSaveResult, setLoopSaveResult] = useState<string | null>(null);
  const [loopSaveError, setLoopSaveError] = useState<string | null>(null);

  // Bot-issue state
  const [botCount, setBotCount] = useState<number | null>(null);
  const [botCountLoading, setBotCountLoading] = useState(false);
  const [closeLoading, setCloseLoading] = useState(false);
  const [closeResult, setCloseResult] = useState<BotIssueResult | null>(null);
  const [closeError, setCloseError] = useState<string | null>(null);

  // Demo seeding state
  const [seedMenuAnchor, setSeedMenuAnchor] = useState<null | HTMLElement>(null);
  const [seeding, setSeeding] = useState(false);
  const [seedResult, setSeedResult] = useState<string | null>(null);
  const [seedError, setSeedError] = useState<string | null>(null);
  const [seedingIssues, setSeedingIssues] = useState(false);
  const [seedIssuesResult, setSeedIssuesResult] = useState<string | null>(null);

  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  const fetchConfig = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiUrl}/config`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json() as Config;
      setCfg(data);
      setLoopIntervalInput(String(data.loop_interval_seconds));
      setMaxInvestigatorsInput(String(data.analyst_max_investigators));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fetch failed");
    } finally {
      setLoading(false);
    }
  }, [apiUrl]);

  const patchConfig = useCallback(async (patch: Partial<Pick<Config, "loop_enabled" | "loop_interval_seconds" | "analyst_max_investigators">>) => {
    const res = await fetch(`${apiUrl}/config`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const updated = await res.json() as Config;
    setCfg((prev) => prev ? { ...prev, ...updated } : prev);
    setLoopIntervalInput(String(updated.loop_interval_seconds));
    setMaxInvestigatorsInput(String(updated.analyst_max_investigators));
    return updated;
  }, [apiUrl]);

  const toggleLoop = useCallback(async () => {
    if (!cfg) return;
    setLoopSaving(true);
    setLoopSaveResult(null);
    setLoopSaveError(null);
    try {
      await patchConfig({ loop_enabled: !cfg.loop_enabled });
    } catch (e) {
      setLoopSaveError(e instanceof Error ? e.message : "Failed");
    } finally {
      setLoopSaving(false);
    }
  }, [cfg, patchConfig]);

  const saveLoopNumbers = useCallback(async () => {
    setLoopSaving(true);
    setLoopSaveResult(null);
    setLoopSaveError(null);
    try {
      await patchConfig({
        loop_interval_seconds: parseInt(loopIntervalInput, 10) || 600,
        analyst_max_investigators: parseInt(maxInvestigatorsInput, 10) || 10,
      });
      setLoopSaveResult("Saved.");
      setTimeout(() => setLoopSaveResult(null), 3000);
    } catch (e) {
      setLoopSaveError(e instanceof Error ? e.message : "Failed");
    } finally {
      setLoopSaving(false);
    }
  }, [loopIntervalInput, maxInvestigatorsInput, patchConfig]);

  const fetchBotCount = useCallback(async () => {
    setBotCountLoading(true);
    try {
      const res = await fetch(`${apiUrl}/gitlab/bot-issues`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setBotCount(json.count as number);
    } catch {
      setBotCount(null);
    } finally {
      setBotCountLoading(false);
    }
  }, [apiUrl]);

  const closeBotIssues = useCallback(async () => {
    setCloseLoading(true);
    setCloseResult(null);
    setCloseError(null);
    try {
      const res = await fetch(`${apiUrl}/gitlab/close-bot-issues`, { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const result = await res.json() as BotIssueResult;
      setCloseResult(result);
      setBotCount((prev) => (prev !== null ? Math.max(0, prev - result.closed) : 0));
    } catch (e) {
      setCloseError(e instanceof Error ? e.message : "Request failed");
    } finally {
      setCloseLoading(false);
    }
  }, [apiUrl]);

  const seedScenario = useCallback(async (scenario: string) => {
    setSeedMenuAnchor(null);
    setSeeding(true);
    setSeedResult(null);
    setSeedError(null);
    try {
      const res = await fetch(`${apiUrl}/demo/seed/${scenario}`, { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setSeedResult(`Seeded scenario: ${scenario}`);
    } catch (e) {
      setSeedError(e instanceof Error ? e.message : "Seed failed");
    } finally {
      setSeeding(false);
    }
  }, [apiUrl]);

  const clearDemoData = useCallback(async () => {
    setSeeding(true);
    setSeedResult(null);
    setSeedError(null);
    try {
      const res = await fetch(`${apiUrl}/graph/demo`, { method: "DELETE" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setSeedResult("Demo data cleared.");
    } catch (e) {
      setSeedError(e instanceof Error ? e.message : "Clear failed");
    } finally {
      setSeeding(false);
    }
  }, [apiUrl]);

  const seedDemoIssues = useCallback(async () => {
    setSeedingIssues(true);
    setSeedIssuesResult(null);
    try {
      const res = await fetch(`${apiUrl}/demo/seed-issues`, { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json() as { seeded: number };
      setSeedIssuesResult(`${json.seeded} stale demo issue${json.seeded === 1 ? "" : "s"} created. Run the pipeline to see them get closed automatically.`);
      // Refresh bot count so Maintenance section updates
      await fetchBotCount();
    } catch (e) {
      setSeedIssuesResult(e instanceof Error ? e.message : "Failed");
    } finally {
      setSeedingIssues(false);
    }
  }, [apiUrl, fetchBotCount]);

  useEffect(() => { fetchConfig(); }, [fetchConfig]);
  useEffect(() => { fetchBotCount(); }, [fetchBotCount]);

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

            {cfg.demo_mode && (
              <>
                <Divider sx={{ borderColor: "rgba(255,255,255,0.04)" }} />
                <Box sx={{ py: 1.5 }}>
                  <Stack spacing={1.5}>
                    <Typography variant="caption" color="text.disabled">
                      Seed synthetic team data into the knowledge graph, or clear all demo entries.
                    </Typography>
                    <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap" }}>
                      <Button
                        variant="outlined"
                        size="small"
                        startIcon={seeding ? <CircularProgress size={13} color="inherit" /> : <ScienceOutlinedIcon fontSize="small" />}
                        disabled={seeding}
                        onClick={(e) => setSeedMenuAnchor(e.currentTarget)}
                        sx={{ fontSize: "0.75rem", textTransform: "none", color: "#a78bfa", borderColor: "#7c3aed", "&:hover": { borderColor: "#a78bfa" } }}
                      >
                        {seeding ? "Seeding…" : "Seed graph data"}
                      </Button>
                      <Menu
                        anchorEl={seedMenuAnchor}
                        open={Boolean(seedMenuAnchor)}
                        onClose={() => setSeedMenuAnchor(null)}
                        slotProps={{ paper: { sx: { bgcolor: "#161b22", border: "1px solid rgba(255,255,255,0.1)" } } }}
                      >
                        {[
                          { id: "team",       label: "Full team",          desc: "alex.chen, priya.sharma, marco.torres, lisa.park" },
                          { id: "new_joiner", label: "New joiner",         desc: "marco.torres - joined, no commits yet" },
                          { id: "fading",     label: "Fading contributor", desc: "priya.sharma - high expertise, inactive 6 months" },
                          { id: "sole_owner", label: "Sole owner",         desc: "scripts/ with one exclusive contributor" },
                        ].map((s) => (
                          <MenuItem key={s.id} onClick={() => seedScenario(s.id)} sx={{ py: 1, flexDirection: "column", alignItems: "flex-start" }}>
                            <Typography variant="body2" color="text.primary">{s.label}</Typography>
                            <Typography variant="caption" color="text.disabled">{s.desc}</Typography>
                          </MenuItem>
                        ))}
                      </Menu>
                      <Button
                        variant="outlined"
                        size="small"
                        disabled={seeding}
                        onClick={clearDemoData}
                        sx={{ fontSize: "0.75rem", textTransform: "none", color: "text.secondary", borderColor: "rgba(255,255,255,0.15)", "&:hover": { borderColor: "rgba(255,255,255,0.3)" } }}
                      >
                        Clear demo data
                      </Button>
                    </Stack>

                    {seedResult && (
                      <Stack direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
                        <CheckCircleOutlinedIcon sx={{ fontSize: 14, color: "success.main" }} />
                        <Typography variant="caption" color="success.main">{seedResult}</Typography>
                      </Stack>
                    )}
                    {seedError && (
                      <Stack direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
                        <ErrorOutlinedIcon sx={{ fontSize: 14, color: "error.main" }} />
                        <Typography variant="caption" color="error.main">{seedError}</Typography>
                      </Stack>
                    )}

                    <Divider sx={{ borderColor: "rgba(255,255,255,0.04)" }} />

                    <Typography variant="caption" color="text.disabled">
                      Seed outdated bot issues into GitLab. The next pipeline run will detect them as stale and close them automatically - demonstrating the issue cleanup flow.
                    </Typography>
                    <Button
                      variant="outlined"
                      size="small"
                      startIcon={seedingIssues ? <CircularProgress size={13} color="inherit" /> : <CodeOutlinedIcon fontSize="small" />}
                      disabled={seedingIssues}
                      onClick={seedDemoIssues}
                      sx={{ alignSelf: "flex-start", fontSize: "0.75rem", textTransform: "none", color: "#a78bfa", borderColor: "#7c3aed", "&:hover": { borderColor: "#a78bfa" } }}
                    >
                      {seedingIssues ? "Creating issues…" : "Seed stale issues"}
                    </Button>
                    {seedIssuesResult && (
                      <Typography variant="caption" color="text.secondary">{seedIssuesResult}</Typography>
                    )}
                  </Stack>
                </Box>
              </>
            )}
          </Section>

          {/* Pipeline loop */}
          <Section icon={<HubOutlinedIcon fontSize="small" />} title="Pipeline Loop">
            <Row
              label="Auto-loop"
              value={
                <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                  <Chip
                    icon={cfg.loop_enabled
                      ? <PlayCircleOutlinedIcon sx={{ fontSize: "14px !important" }} />
                      : <PauseCircleOutlinedIcon sx={{ fontSize: "14px !important" }} />}
                    label={cfg.loop_enabled ? "Enabled" : "Disabled"}
                    size="small"
                    color={cfg.loop_enabled ? "success" : "default"}
                    variant="outlined"
                    sx={{ height: 22, fontSize: "0.7rem" }}
                  />
                  <Button
                    size="small"
                    variant="outlined"
                    disabled={loopSaving}
                    onClick={toggleLoop}
                    sx={{ height: 24, fontSize: "0.7rem", textTransform: "none", minWidth: 62,
                      color: cfg.loop_enabled ? "error.main" : "success.main",
                      borderColor: cfg.loop_enabled ? "error.dark" : "success.dark",
                    }}
                  >
                    {cfg.loop_enabled ? "Disable" : "Enable"}
                  </Button>
                </Stack>
              }
            />
            <Divider sx={{ borderColor: "rgba(255,255,255,0.04)" }} />
            <Row
              label="Interval (seconds)"
              value={
                <Stack direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
                  <TextField
                    size="small"
                    type="number"
                    value={loopIntervalInput}
                    onChange={(e) => { setLoopIntervalInput(e.target.value); setLoopSaveResult(null); }}
                    slotProps={{ htmlInput: { min: 60, max: 86400 } }}
                    sx={{ width: 100, "& .MuiInputBase-input": { py: 0.6, fontSize: "0.8rem", fontFamily: "var(--font-google-sans-code)" } }}
                  />
                  <Typography variant="caption" color="text.disabled">
                    {parseInt(loopIntervalInput, 10) >= 60
                      ? `(${Math.round(parseInt(loopIntervalInput, 10) / 60)}m)`
                      : ""}
                  </Typography>
                </Stack>
              }
            />
            <Divider sx={{ borderColor: "rgba(255,255,255,0.04)" }} />
            <Row
              label="Max investigators"
              value={
                <Stack direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
                  <TextField
                    size="small"
                    type="number"
                    value={maxInvestigatorsInput}
                    onChange={(e) => { setMaxInvestigatorsInput(e.target.value); setLoopSaveResult(null); }}
                    slotProps={{ htmlInput: { min: 1, max: 20 } }}
                    sx={{ width: 80, "& .MuiInputBase-input": { py: 0.6, fontSize: "0.8rem", fontFamily: "var(--font-google-sans-code)" } }}
                  />
                  <Typography variant="caption" color="text.disabled">concurrent</Typography>
                </Stack>
              }
            />
            <Box sx={{ py: 1.5 }}>
              <Stack spacing={1}>
                <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
                  <Button
                    size="small"
                    variant="outlined"
                    disabled={loopSaving
                      || (loopIntervalInput === String(cfg.loop_interval_seconds)
                          && maxInvestigatorsInput === String(cfg.analyst_max_investigators))}
                    onClick={saveLoopNumbers}
                    sx={{ fontSize: "0.75rem", textTransform: "none" }}
                  >
                    {loopSaving ? "Saving…" : "Save changes"}
                  </Button>
                  {loopSaveResult && (
                    <Stack direction="row" spacing={0.5} sx={{ alignItems: "center" }}>
                      <CheckCircleOutlinedIcon sx={{ fontSize: 13, color: "success.main" }} />
                      <Typography variant="caption" color="success.main">{loopSaveResult}</Typography>
                    </Stack>
                  )}
                  {loopSaveError && (
                    <Stack direction="row" spacing={0.5} sx={{ alignItems: "center" }}>
                      <ErrorOutlinedIcon sx={{ fontSize: 13, color: "error.main" }} />
                      <Typography variant="caption" color="error.main">{loopSaveError}</Typography>
                    </Stack>
                  )}
                </Stack>
                {!cfg.loop_enabled && (
                  <Typography variant="caption" color="text.disabled">
                    Loop off - trigger runs manually via the Pipeline page or{" "}
                    <Box component="span" sx={{ fontFamily: "var(--font-google-sans-code)", color: "text.secondary" }}>POST /pipeline/run</Box>.
                  </Typography>
                )}
              </Stack>
            </Box>
          </Section>

          {/* Maintenance */}
          <Section icon={<DeleteOutlinedIcon fontSize="small" />} title="Maintenance">
            <Row
              label="Open bot issues"
              value={
                <Stack direction="row" sx={{ alignItems: "center" }} spacing={1}>
                  {botCountLoading ? (
                    <CircularProgress size={14} />
                  ) : (
                    <Typography variant="body2" color={botCount === 0 ? "text.disabled" : "text.primary"} sx={{ fontFamily: "var(--font-google-sans-code)" }}>
                      {botCount === null ? "-" : botCount}
                    </Typography>
                  )}
                  <IconButton size="small" onClick={fetchBotCount} disabled={botCountLoading} sx={{ color: "text.secondary" }}>
                    <RefreshIcon sx={{ fontSize: 14 }} />
                  </IconButton>
                </Stack>
              }
            />
            <Divider sx={{ borderColor: "rgba(255,255,255,0.04)" }} />
            <Box sx={{ py: 1.5 }}>
              <Stack spacing={1.5}>
                <Typography variant="caption" color="text.disabled">
                  Closes all open GitLab issues authored by the Mycelium bot or carrying the{" "}
                  <Box component="span" sx={{ fontFamily: "var(--font-google-sans-code)", color: "text.secondary" }}>mycelium</Box>{" "}
                  label. Each issue receives a closing comment before being closed.
                </Typography>

                <Button
                  variant="outlined"
                  size="small"
                  color="error"
                  startIcon={closeLoading ? <CircularProgress size={14} color="inherit" /> : <DeleteOutlinedIcon fontSize="small" />}
                  disabled={closeLoading || botCount === 0}
                  onClick={closeBotIssues}
                  sx={{ alignSelf: "flex-start", fontSize: "0.75rem", textTransform: "none" }}
                >
                  {closeLoading ? "Closing issues…" : `Close bot issues${botCount !== null && botCount > 0 ? ` (${botCount})` : ""}`}
                </Button>

                {closeResult && (
                  <Stack direction="row" sx={{ alignItems: "center" }} spacing={0.75}>
                    <CheckCircleOutlinedIcon sx={{ fontSize: 14, color: "success.main" }} />
                    <Typography variant="caption" color="success.main">
                      {closeResult.closed} closed
                      {closeResult.errors > 0 ? `, ${closeResult.errors} errors` : ""}
                      {" "}of {closeResult.total} bot issues.
                    </Typography>
                  </Stack>
                )}

                {closeError && (
                  <Stack direction="row" sx={{ alignItems: "center" }} spacing={0.75}>
                    <ErrorOutlinedIcon sx={{ fontSize: 14, color: "error.main" }} />
                    <Typography variant="caption" color="error.main">{closeError}</Typography>
                  </Stack>
                )}
              </Stack>
            </Box>
          </Section>
        </>
      )}
    </Stack>
  );
}
