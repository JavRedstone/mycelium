"use client";

import { useCallback, useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import LinearProgress from "@mui/material/LinearProgress";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import IconButton from "@mui/material/IconButton";

import CallSplitOutlinedIcon from "@mui/icons-material/CallSplitOutlined";
import CommitOutlinedIcon from "@mui/icons-material/CommitOutlined";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutlined";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowRightIcon from "@mui/icons-material/KeyboardArrowRight";
import RefreshOutlinedIcon from "@mui/icons-material/RefreshOutlined";
import ScienceOutlinedIcon from "@mui/icons-material/ScienceOutlined";
import StarBorderOutlinedIcon from "@mui/icons-material/StarBorderOutlined";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Deterministic mock commit messages per module path
const MOCK_COMMITS: Record<string, string> = {
  app:      "refactor: update HTTP handler registration and routing",
  internal: "fix: resolve race condition in connection pool shutdown",
  scripts:  "feat: add retry logic for deployment scripts",
  shared:   "chore: remove deprecated helper functions and types",
  test:     "test: add coverage for edge cases in auth flow",
};
function mockCommit(path: string) {
  return MOCK_COMMITS[path] ?? `chore: update ${path}/ dependencies`;
}

type ProjectInfo = {
  id: number;
  name: string;
  path: string;
  path_with_namespace: string;
  namespace_name: string;
  namespace_path: string;
  web_url: string;
  default_branch: string;
  description?: string;
  star_count: number;
  forks_count: number;
  is_fork: boolean;
};

// ── helpers ──────────────────────────────────────────────────────────────────

function timeAgo(dateStr?: string): string {
  if (!dateStr) return "—";
  const ms = Date.now() - new Date(dateStr).getTime();
  const days = Math.floor(ms / 86_400_000);
  if (days === 0) return "today";
  if (days === 1) return "yesterday";
  if (days < 30) return `${days} days ago`;
  const months = Math.round(days / 30);
  return months === 1 ? "1 month ago" : `${months} months ago`;
}

function initials(name: string): string {
  return name
    .split(" ")
    .map((w) => w[0] ?? "")
    .join("")
    .toUpperCase()
    .slice(0, 2);
}

const AVATAR_PALETTE = ["#1a73e8", "#34a853", "#fbbc04", "#ea4335", "#00bcd4", "#9c27b0"];
function avatarColor(seed: string, demo?: boolean) {
  if (demo) return "#7c3aed";
  return AVATAR_PALETTE[seed.charCodeAt(0) % AVATAR_PALETTE.length];
}

// ── sub-components ────────────────────────────────────────────────────────────

function DevAvatar({
  name,
  demo,
  size = 22,
}: {
  name: string;
  demo?: boolean;
  size?: number;
}) {
  return (
    <Tooltip title={name} arrow placement="top">
      <Box
        sx={{
          width: size,
          height: size,
          borderRadius: "50%",
          bgcolor: avatarColor(name, demo),
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          fontSize: size * 0.38,
          fontWeight: 700,
          color: "#fff",
          flexShrink: 0,
          fontFamily: "monospace",
          border: demo ? "1.5px solid #a78bfa" : "none",
          cursor: "default",
        }}
      >
        {initials(name)}
      </Box>
    </Tooltip>
  );
}

// ── types ─────────────────────────────────────────────────────────────────────

type Contributor = {
  developer_username: string;
  commit_count: number;
  lines_changed: number;
  expertise_score: number;
  last_contribution_at?: string;
  external?: boolean;
  demo?: boolean;
};

type Module = {
  path: string;
  language?: string;
  bus_factor: number;
  owners: string[];
  last_commit_at?: string;
  demo?: boolean;
  contributors: Contributor[];
};

type Developer = {
  username: string;
  name: string;
  active?: boolean;
  last_seen?: string;
  demo?: boolean;
  external?: boolean;
};

// ── risk classification ───────────────────────────────────────────────────────

type Risk = "critical" | "warning" | "caution" | "healthy";

function classifyRisk(mod: Module, devMap: Record<string, Developer>): Risk {
  const internal = mod.contributors.filter((c) => !c.external);
  if (internal.length === 0) return "caution";

  const primary = internal.reduce((a, b) =>
    a.expertise_score > b.expertise_score ? a : b
  );
  const dev = devMap[primary.developer_username];
  const lastSeenMs = dev?.last_seen
    ? Date.now() - new Date(dev.last_seen).getTime()
    : (primary.last_contribution_at
        ? Date.now() - new Date(primary.last_contribution_at).getTime()
        : 0);
  const inactiveDays = lastSeenMs / 86_400_000;

  if (mod.bus_factor <= 1 && inactiveDays > 60) return "critical";
  if (mod.bus_factor <= 1) return "warning";
  if (mod.bus_factor === 2) return "caution";
  return "healthy";
}

const RISK_STYLES: Record<Risk, { border: string; bg: string; label: string; color: string }> = {
  critical: {
    border: "#ea4335",
    bg:     "rgba(234,67,53,0.06)",
    label:  "Sole owner · inactive",
    color:  "#ea4335",
  },
  warning: {
    border: "#fbbc04",
    bg:     "rgba(251,188,4,0.05)",
    label:  "Sole owner",
    color:  "#fbbc04",
  },
  caution: {
    border: "#1a73e8",
    bg:     "rgba(26,115,232,0.04)",
    label:  "Low coverage",
    color:  "#4fc3f7",
  },
  healthy: {
    border: "transparent",
    bg:     "transparent",
    label:  "Healthy",
    color:  "#34a853",
  },
};

// ── contributor detail panel ──────────────────────────────────────────────────

function ContributorDetail({
  mod,
  devMap,
  risk,
}: {
  mod: Module;
  devMap: Record<string, Developer>;
  risk: Risk;
}) {
  const internal = [...mod.contributors]
    .filter((c) => !c.external)
    .sort((a, b) => b.expertise_score - a.expertise_score);
  const external = mod.contributors.filter((c) => c.external);

  const riskStyle = RISK_STYLES[risk];

  return (
    <Box
      sx={{
        px: 3,
        py: 2,
        bgcolor: "rgba(255,255,255,0.02)",
        borderTop: "1px solid rgba(255,255,255,0.06)",
      }}
    >
      <Stack spacing={2}>
        {/* Risk callout */}
        {risk !== "healthy" && (
          <Stack direction="row" spacing={1} sx={{ alignItems: "flex-start" }}>
            <WarningAmberIcon sx={{ fontSize: 15, color: riskStyle.color, mt: 0.15, flexShrink: 0 }} />
            <Typography variant="caption" sx={{ color: riskStyle.color, lineHeight: 1.5 }}>
              {risk === "critical" &&
                `${internal[0]?.developer_username ?? "The sole contributor"} owns ${Math.round((internal[0]?.expertise_score ?? 0) * 100)}% of this module and has been inactive for over two months. No backup exists.`}
              {risk === "warning" &&
                `Only one contributor has ever committed to this module. If they become unavailable, this module has no coverage.`}
              {risk === "caution" &&
                `This module has limited coverage. Consider cross-training a second contributor.`}
            </Typography>
          </Stack>
        )}

        {/* Internal contributors */}
        <Box>
          <Typography variant="caption" color="text.disabled" sx={{ mb: 1, display: "block", textTransform: "uppercase", letterSpacing: "0.08em", fontSize: "0.63rem" }}>
            Team contributors
          </Typography>
          <Stack spacing={1.25}>
            {internal.length === 0 ? (
              <Typography variant="caption" color="text.disabled">
                No internal contributors — all commits are from upstream authors.
              </Typography>
            ) : (
              internal.map((c) => {
                const dev = devMap[c.developer_username];
                const displayName = dev?.name ?? c.developer_username;
                const lastSeen = dev?.last_seen ?? c.last_contribution_at;
                const inactive =
                  lastSeen && Date.now() - new Date(lastSeen).getTime() > 60 * 86_400_000;

                return (
                  <Stack key={c.developer_username} spacing={0.5}>
                    <Stack direction="row" sx={{ alignItems: "center", gap: 1 }}>
                      <DevAvatar name={displayName} demo={c.demo || dev?.demo} size={20} />
                      <Typography variant="caption" color="text.primary" sx={{ fontWeight: 600, flex: 1 }}>
                        {displayName}
                      </Typography>
                      {c.demo && (
                        <Chip
                          label="demo"
                          size="small"
                          icon={<ScienceOutlinedIcon />}
                          sx={{
                            height: 16,
                            fontSize: "0.6rem",
                            bgcolor: "rgba(167,139,250,0.12)",
                            color: "#a78bfa",
                            border: "1px solid rgba(167,139,250,0.3)",
                            "& .MuiChip-icon": { fontSize: 10, color: "#a78bfa" },
                            "& .MuiChip-label": { px: 0.75 },
                          }}
                        />
                      )}
                      {inactive && (
                        <Chip
                          label="inactive"
                          size="small"
                          sx={{
                            height: 16,
                            fontSize: "0.6rem",
                            bgcolor: "rgba(234,67,53,0.1)",
                            color: "#ea4335",
                            border: "1px solid rgba(234,67,53,0.25)",
                            "& .MuiChip-label": { px: 0.75 },
                          }}
                        />
                      )}
                      <Typography variant="caption" color="text.disabled" sx={{ fontFamily: "monospace", fontSize: "0.7rem" }}>
                        {c.commit_count} commits · {timeAgo(lastSeen)}
                      </Typography>
                    </Stack>
                    <Stack direction="row" spacing={1} sx={{ alignItems: "center", pl: "28px" }}>
                      <LinearProgress
                        variant="determinate"
                        value={Math.round(c.expertise_score * 100)}
                        sx={{
                          flex: 1,
                          height: 4,
                          borderRadius: 2,
                          bgcolor: "rgba(255,255,255,0.07)",
                          "& .MuiLinearProgress-bar": {
                            bgcolor: inactive ? "#ea4335" : c.demo ? "#a78bfa" : "#1a73e8",
                            borderRadius: 2,
                          },
                        }}
                      />
                      <Typography variant="caption" color="text.secondary" sx={{ fontFamily: "monospace", fontSize: "0.68rem", minWidth: 30 }}>
                        {Math.round(c.expertise_score * 100)}%
                      </Typography>
                    </Stack>
                  </Stack>
                );
              })
            )}
          </Stack>
        </Box>

        {/* Upstream authors */}
        {external.length > 0 && (
          <Box>
            <Typography variant="caption" color="text.disabled" sx={{ mb: 1, display: "block", textTransform: "uppercase", letterSpacing: "0.08em", fontSize: "0.63rem" }}>
              Upstream authors (unreachable)
            </Typography>
            <Stack spacing={0.75}>
              {external.map((c) => {
                const dev = devMap[c.developer_username];
                const displayName = dev?.name ?? c.developer_username;
                return (
                  <Stack key={c.developer_username} direction="row" spacing={1} sx={{ alignItems: "center" }}>
                    <DevAvatar name={displayName} size={18} />
                    <Typography variant="caption" color="text.disabled">
                      {displayName}
                    </Typography>
                    <Typography variant="caption" color="text.disabled" sx={{ fontFamily: "monospace", fontSize: "0.68rem" }}>
                      · {c.commit_count} commits
                    </Typography>
                  </Stack>
                );
              })}
            </Stack>
            <Typography variant="caption" color="text.disabled" sx={{ display: "block", mt: 1, lineHeight: 1.5, fontStyle: "italic" }}>
              Upstream commits are not counted toward bus factor — these contributors are not on the current team.
            </Typography>
          </Box>
        )}

        {/* Bus factor */}
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
          <Typography variant="caption" color="text.disabled">
            Bus factor:
          </Typography>
          <Chip
            label={mod.bus_factor}
            size="small"
            sx={{
              height: 18,
              fontSize: "0.7rem",
              fontFamily: "monospace",
              bgcolor:
                mod.bus_factor === 0
                  ? "rgba(234,67,53,0.15)"
                  : mod.bus_factor === 1
                  ? "rgba(251,188,4,0.12)"
                  : "rgba(52,168,83,0.12)",
              color:
                mod.bus_factor === 0
                  ? "#ea4335"
                  : mod.bus_factor === 1
                  ? "#fbbc04"
                  : "#34a853",
              border: "none",
              "& .MuiChip-label": { px: 0.75 },
            }}
          />
          {mod.language && (
            <Typography variant="caption" color="text.disabled">
              · {mod.language}
            </Typography>
          )}
        </Stack>
      </Stack>
    </Box>
  );
}

// ── module row ────────────────────────────────────────────────────────────────

function ModuleRow({
  mod,
  devMap,
  expanded,
  onToggle,
}: {
  mod: Module;
  devMap: Record<string, Developer>;
  expanded: boolean;
  onToggle: () => void;
}) {
  const risk = classifyRisk(mod, devMap);
  const riskStyle = RISK_STYLES[risk];

  // Primary contributor = highest expertise internal
  const internal = mod.contributors.filter((c) => !c.external);
  const primary = internal.length
    ? internal.reduce((a, b) => (a.expertise_score > b.expertise_score ? a : b))
    : null;
  const primaryDev = primary ? devMap[primary.developer_username] : null;
  const primaryName = primaryDev?.name ?? primary?.developer_username ?? "—";

  // Last activity = most recent contribution across all internal contributors
  const lastActivity = internal
    .map((c) => (c.last_contribution_at ? new Date(c.last_contribution_at).getTime() : 0))
    .reduce((a, b) => Math.max(a, b), 0);
  const lastActivityStr = lastActivity ? new Date(lastActivity).toISOString() : mod.last_commit_at;

  return (
    <Box>
      <Box
        onClick={onToggle}
        sx={{
          display: "grid",
          gridTemplateColumns: "20px 1fr auto auto",
          gap: 1.5,
          alignItems: "center",
          px: 2.5,
          py: 1.25,
          cursor: "pointer",
          borderLeft: `3px solid ${riskStyle.border}`,
          bgcolor: expanded ? "rgba(255,255,255,0.03)" : riskStyle.bg,
          "&:hover": { bgcolor: "rgba(255,255,255,0.04)" },
          transition: "background 0.15s",
        }}
      >
        {/* Expand toggle */}
        <Box sx={{ color: "text.disabled", display: "flex" }}>
          {expanded ? (
            <KeyboardArrowDownIcon sx={{ fontSize: 16 }} />
          ) : (
            <KeyboardArrowRightIcon sx={{ fontSize: 16 }} />
          )}
        </Box>

        {/* Name + commit message */}
        <Stack direction="row" spacing={1.5} sx={{ alignItems: "center", minWidth: 0 }}>
          <FolderOutlinedIcon sx={{ fontSize: 16, color: "#fbbc04", flexShrink: 0 }} />
          <Typography
            variant="body2"
            sx={{ fontFamily: "monospace", fontWeight: 600, color: "text.primary", flexShrink: 0 }}
          >
            {mod.path}/
          </Typography>
          {mod.demo && (
            <Chip
              label="demo"
              size="small"
              icon={<ScienceOutlinedIcon />}
              sx={{
                height: 16,
                fontSize: "0.6rem",
                bgcolor: "rgba(167,139,250,0.1)",
                color: "#a78bfa",
                border: "1px solid rgba(167,139,250,0.25)",
                flexShrink: 0,
                "& .MuiChip-icon": { fontSize: 9, color: "#a78bfa" },
                "& .MuiChip-label": { px: 0.75 },
              }}
            />
          )}
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              flexShrink: 1,
            }}
          >
            {mockCommit(mod.path)}
          </Typography>
        </Stack>

        {/* Author + avatars */}
        <Stack direction="row" spacing={0.75} sx={{ alignItems: "center", flexShrink: 0 }}>
          {primary && (
            <DevAvatar name={primaryName} demo={primary.demo || primaryDev?.demo} size={20} />
          )}
          {risk !== "healthy" && (
            <Tooltip title={riskStyle.label} arrow placement="top">
              <Chip
                label={riskStyle.label}
                size="small"
                icon={<ErrorOutlineIcon />}
                sx={{
                  height: 18,
                  fontSize: "0.62rem",
                  bgcolor: `${riskStyle.color}18`,
                  color: riskStyle.color,
                  border: `1px solid ${riskStyle.color}40`,
                  "& .MuiChip-icon": { fontSize: 11, color: riskStyle.color },
                  "& .MuiChip-label": { px: 0.75 },
                }}
              />
            </Tooltip>
          )}
        </Stack>

        {/* Timestamp */}
        <Typography
          variant="caption"
          color={risk === "critical" ? "#ea4335" : "text.disabled"}
          sx={{ fontFamily: "monospace", fontSize: "0.7rem", flexShrink: 0, minWidth: 90, textAlign: "right" }}
        >
          {timeAgo(lastActivityStr)}
        </Typography>
      </Box>

      <Collapse in={expanded} unmountOnExit>
        <ContributorDetail mod={mod} devMap={devMap} risk={risk} />
      </Collapse>

      <Divider sx={{ borderColor: "rgba(255,255,255,0.05)" }} />
    </Box>
  );
}

// ── main component ────────────────────────────────────────────────────────────

export default function MockRepo() {
  const [modules, setModules] = useState<Module[]>([]);
  const [devMap, setDevMap] = useState<Record<string, Developer>>({});
  const [project, setProject] = useState<ProjectInfo | null>(null);
  const [loading, setLoading] = useState(true);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [hasDemo, setHasDemo] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [graphRes, devRes, projectRes] = await Promise.all([
        fetch(`${API}/graph`),
        fetch(`${API}/developers`),
        fetch(`${API}/project`),
      ]);
      const graph = await graphRes.json();
      const devData = await devRes.json();
      if (projectRes.ok) setProject(await projectRes.json());

      const map: Record<string, Developer> = {};
      for (const d of devData.developers ?? []) map[d.username] = d;

      const mods: Module[] = (graph.modules ?? []).sort((a: Module, b: Module) => {
        const riskOrder: Record<Risk, number> = { critical: 0, warning: 1, caution: 2, healthy: 3 };
        return riskOrder[classifyRisk(a, map)] - riskOrder[classifyRisk(b, map)];
      });

      setModules(mods);
      setDevMap(map);
      setHasDemo(mods.some((m) => m.demo || m.contributors.some((c) => c.demo)));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Compute repo-level summary
  const totalContributors = Object.values(devMap).filter((d) => !d.external).length;
  const latestActivity = modules
    .flatMap((m) => m.contributors.map((c) => c.last_contribution_at ?? ""))
    .filter(Boolean)
    .sort()
    .at(-1);

  // Header "latest commit" — the most recent contribution across all modules
  const latestContrib = modules
    .flatMap((m) => m.contributors.map((c) => ({ ...c, module: m.path })))
    .filter((c) => !c.external && c.last_contribution_at)
    .sort((a, b) =>
      new Date(b.last_contribution_at!).getTime() - new Date(a.last_contribution_at!).getTime()
    )[0];
  const latestDev = latestContrib ? devMap[latestContrib.developer_username] : null;
  const latestName = latestDev?.name ?? latestContrib?.developer_username ?? "—";

  return (
    <Stack spacing={2.5}>
      {/* Demo banner */}
      {hasDemo && (
        <Paper
          variant="outlined"
          sx={{
            px: 2.5,
            py: 1.5,
            borderColor: "rgba(167,139,250,0.3)",
            bgcolor: "rgba(167,139,250,0.07)",
            borderRadius: 2,
          }}
        >
          <Stack direction="row" spacing={1.25} sx={{ alignItems: "center" }}>
            <ScienceOutlinedIcon sx={{ fontSize: 16, color: "#a78bfa", flexShrink: 0 }} />
            <Typography variant="body2" sx={{ color: "#c4b5fd" }}>
              This repository view contains{" "}
              <strong>seeded demo data</strong> — entries marked with a purple chip are
              synthetic. Run{" "}
              <Box component="code" sx={{ fontFamily: "monospace", bgcolor: "rgba(255,255,255,0.08)", px: 0.5, borderRadius: 0.5 }}>
                python -m scripts.seed_scenarios team
              </Box>{" "}
              to refresh or use the Knowledge Graph page to clear demo data.
            </Typography>
          </Stack>
        </Paper>
      )}

      {/* GitLab-style project header */}
      <Paper
        variant="outlined"
        sx={{ borderColor: "rgba(255,255,255,0.1)", borderRadius: 2, overflow: "hidden" }}
      >
        {/* Top bar: project name + actions */}
        <Box sx={{ px: 2.5, py: 1.75, display: "flex", alignItems: "center", gap: 2 }}>
          <Stack direction="row" spacing={0.75} sx={{ alignItems: "center", flex: 1, minWidth: 0 }}>
            {project ? (
              <>
                <Typography
                  component="a"
                  href={project.web_url.replace(`/${project.path}`, "")}
                  target="_blank"
                  rel="noopener"
                  variant="body2"
                  color="text.secondary"
                  sx={{ textDecoration: "none", "&:hover": { textDecoration: "underline" } }}
                >
                  {project.namespace_name || project.namespace_path}
                </Typography>
                <Typography variant="body2" color="text.disabled">/</Typography>
                <Typography
                  component="a"
                  href={project.web_url}
                  target="_blank"
                  rel="noopener"
                  variant="body2"
                  sx={{ fontWeight: 700, color: "primary.light", textDecoration: "none", "&:hover": { textDecoration: "underline" } }}
                >
                  {project.name}
                </Typography>
                <Typography variant="caption" color="text.disabled" sx={{ fontFamily: "monospace", fontSize: "0.65rem" }}>
                  #{project.id}
                </Typography>
                {project.is_fork && (
                  <Chip label="fork" size="small" sx={{ height: 16, fontSize: "0.6rem", color: "text.disabled", borderColor: "rgba(255,255,255,0.12)", "& .MuiChip-label": { px: 0.75 } }} variant="outlined" />
                )}
              </>
            ) : (
              <Typography variant="body2" color="text.disabled">Loading project…</Typography>
            )}
          </Stack>
          <Stack direction="row" spacing={1}>
            {project && (
              <>
                <Chip
                  icon={<StarBorderOutlinedIcon sx={{ fontSize: "14px !important" }} />}
                  label={`Star ${project.star_count}`}
                  size="small"
                  variant="outlined"
                  sx={{ height: 24, fontSize: "0.72rem", borderColor: "rgba(255,255,255,0.15)", color: "text.secondary" }}
                />
                <Chip
                  icon={<CallSplitOutlinedIcon sx={{ fontSize: "14px !important" }} />}
                  label={`Fork ${project.forks_count}`}
                  size="small"
                  variant="outlined"
                  sx={{ height: 24, fontSize: "0.72rem", borderColor: "rgba(255,255,255,0.15)", color: "text.secondary" }}
                />
              </>
            )}
          </Stack>
          <IconButton size="small" onClick={load} sx={{ color: "text.disabled" }}>
            <RefreshOutlinedIcon sx={{ fontSize: 16 }} />
          </IconButton>
        </Box>

        <Divider sx={{ borderColor: "rgba(255,255,255,0.08)" }} />

        {/* Latest commit bar */}
        {latestContrib && (
          <Box sx={{ px: 2.5, py: 1.25, bgcolor: "rgba(255,255,255,0.02)" }}>
            <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
              <CommitOutlinedIcon sx={{ fontSize: 14, color: "text.disabled", flexShrink: 0 }} />
              <Typography variant="caption" sx={{ fontFamily: "monospace", color: "text.secondary", flex: 1 }}>
                <Box component="span" sx={{ color: "text.primary", fontWeight: 600 }}>
                  {latestName}
                </Box>
                {" committed "}
                <Box component="span" sx={{ color: "primary.light" }}>
                  {mockCommit(latestContrib.module)}
                </Box>
              </Typography>
              <Typography variant="caption" color="text.disabled" sx={{ fontFamily: "monospace", fontSize: "0.7rem", flexShrink: 0 }}>
                {timeAgo(latestContrib.last_contribution_at)}
              </Typography>
            </Stack>
          </Box>
        )}

        <Divider sx={{ borderColor: "rgba(255,255,255,0.08)" }} />

        {/* Branch + stats row */}
        <Box sx={{ px: 2.5, py: 1.25 }}>
          <Stack direction="row" spacing={3} sx={{ alignItems: "center" }}>
            <Stack direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
              <CallSplitOutlinedIcon sx={{ fontSize: 13, color: "text.disabled" }} />
              <Typography variant="caption" sx={{ fontFamily: "monospace", color: "text.secondary", fontWeight: 600 }}>
                {project?.default_branch ?? "main"}
              </Typography>
            </Stack>
            <Typography variant="caption" color="text.disabled">
              {modules.length} director{modules.length === 1 ? "y" : "ies"}
            </Typography>
            <Typography variant="caption" color="text.disabled">
              {totalContributors} contributor{totalContributors !== 1 ? "s" : ""}
            </Typography>
            {latestActivity && (
              <Typography variant="caption" color="text.disabled">
                Last activity {timeAgo(latestActivity)}
              </Typography>
            )}
          </Stack>
        </Box>

        <Divider sx={{ borderColor: "rgba(255,255,255,0.08)" }} />

        {/* Column headers */}
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: "20px 1fr auto auto",
            gap: 1.5,
            px: 2.5,
            py: 0.75,
            bgcolor: "rgba(255,255,255,0.02)",
          }}
        >
          <Box />
          <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.68rem", textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Name
          </Typography>
          <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.68rem", textTransform: "uppercase", letterSpacing: "0.06em" }}>
            Status
          </Typography>
          <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.68rem", textTransform: "uppercase", letterSpacing: "0.06em", textAlign: "right" }}>
            Last commit
          </Typography>
        </Box>

        <Divider sx={{ borderColor: "rgba(255,255,255,0.08)" }} />

        {/* Module rows */}
        {loading ? (
          <Box sx={{ px: 2.5, py: 4, display: "flex", justifyContent: "center" }}>
            <CircularProgress size={24} />
          </Box>
        ) : modules.length === 0 ? (
          <Box sx={{ px: 2.5, py: 4, textAlign: "center" }}>
            <Typography variant="body2" color="text.disabled">
              No modules in the knowledge graph yet. Run the pipeline or seed demo data.
            </Typography>
          </Box>
        ) : (
          modules.map((mod) => (
            <ModuleRow
              key={mod.path}
              mod={mod}
              devMap={devMap}
              expanded={expanded === mod.path}
              onToggle={() => setExpanded(expanded === mod.path ? null : mod.path)}
            />
          ))
        )}
      </Paper>

      {/* Legend */}
      <Stack direction="row" spacing={2.5} sx={{ px: 0.5 }}>
        {([
          { color: "#ea4335", label: "Sole owner · inactive (critical)" },
          { color: "#fbbc04", label: "Sole owner · active (warning)" },
          { color: "#4fc3f7", label: "Low coverage" },
          { color: "rgba(255,255,255,0.2)", label: "Healthy" },
        ] as const).map(({ color, label }) => (
          <Stack key={label} direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
            <Box sx={{ width: 3, height: 14, borderRadius: 1, bgcolor: color, flexShrink: 0 }} />
            <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.68rem" }}>
              {label}
            </Typography>
          </Stack>
        ))}
      </Stack>
    </Stack>
  );
}
