"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import List from "@mui/material/List";
import ListItem from "@mui/material/ListItem";
import ListItemButton from "@mui/material/ListItemButton";
import ListItemIcon from "@mui/material/ListItemIcon";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import AccountTreeOutlinedIcon from "@mui/icons-material/AccountTreeOutlined";
import BarChartOutlinedIcon from "@mui/icons-material/BarChartOutlined";
import BiotechOutlinedIcon from "@mui/icons-material/BiotechOutlined";
import BoltOutlinedIcon from "@mui/icons-material/BoltOutlined";
import ChatOutlinedIcon from "@mui/icons-material/ChatOutlined";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import HistoryOutlinedIcon from "@mui/icons-material/HistoryOutlined";
import HubOutlinedIcon from "@mui/icons-material/HubOutlined";
import PlayArrowOutlinedIcon from "@mui/icons-material/PlayArrowOutlined";
import ScienceOutlinedIcon from "@mui/icons-material/ScienceOutlined";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import TerminalOutlinedIcon from "@mui/icons-material/TerminalOutlined";
import TimelineOutlinedIcon from "@mui/icons-material/TimelineOutlined";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type NavItem = { label: string; href: string; icon: React.ReactNode; primary?: boolean };

type PipelineStatus = {
  status: string;       // "running" | "success" | "failed" | "partial" | "cancelled"
  progress: number;     // 0–100 (completed stages / total stages)
  stagesDone: number;
  stagesTotal: number;
} | null;

// ---------------------------------------------------------------------------
// Nav structure
// ---------------------------------------------------------------------------

const NAV_GROUPS: { section: string; items: NavItem[] }[] = [
  {
    section: "Pipeline",
    items: [
      { label: "Pipeline",        href: "/pipeline",       icon: <PlayArrowOutlinedIcon fontSize="small" />, primary: true },
      { label: "Agent Activity",  href: "/activity",       icon: <ChatOutlinedIcon fontSize="small" /> },
      { label: "Logs",            href: "/logs",           icon: <TerminalOutlinedIcon fontSize="small" /> },
      { label: "Actions",         href: "/actions",        icon: <BoltOutlinedIcon fontSize="small" /> },
      { label: "Run History",     href: "/timeline",       icon: <TimelineOutlinedIcon fontSize="small" /> },
      { label: "Investigations",  href: "/investigations", icon: <BiotechOutlinedIcon fontSize="small" /> },
      { label: "Analytics",       href: "/analytics",      icon: <BarChartOutlinedIcon fontSize="small" /> },
    ],
  },
  {
    section: "Repository",
    items: [
      { label: "Repository",      href: "/repo",    icon: <FolderOutlinedIcon fontSize="small" /> },
      { label: "Repo History",    href: "/history", icon: <HistoryOutlinedIcon fontSize="small" /> },
      { label: "Knowledge Graph", href: "/graph",   icon: <AccountTreeOutlinedIcon fontSize="small" /> },
    ],
  },
];

const BOTTOM_ITEM: NavItem = {
  label: "Configuration",
  href: "/config",
  icon: <SettingsOutlinedIcon fontSize="small" />,
};

// ---------------------------------------------------------------------------
// Pipeline status polling hook
// ---------------------------------------------------------------------------

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function usePipelineStatus(): PipelineStatus {
  const [status, setStatus] = useState<PipelineStatus>(null);

  useEffect(() => {
    let cancelled = false;

    async function poll() {
      try {
        const res = await fetch(`${API}/pipeline/current`);
        if (!res.ok || cancelled) return;
        const data = await res.json();
        const run = data?.run;
        if (!run) { setStatus(null); return; }

        const stages = (run.stages ?? []) as Array<{ status: string }>;
        const terminal = new Set(["success", "failed", "skipped", "cancelled"]);
        const done = stages.filter((s) => terminal.has(s.status)).length;
        const total = stages.length || 1;

        setStatus({
          status: run.status ?? "unknown",
          progress: Math.round((done / total) * 100),
          stagesDone: done,
          stagesTotal: total,
        });
      } catch {
        // backend unreachable - leave status unchanged
      }
    }

    poll();
    const id = setInterval(poll, 4000);
    return () => { cancelled = true; clearInterval(id); };
  }, []);

  return status;
}

// ---------------------------------------------------------------------------
// Demo mode hook
// ---------------------------------------------------------------------------

function useDemoMode(): boolean {
  const [demo, setDemo] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch(`${API}/config`)
      .then((r) => r.ok ? r.json() : null)
      .then((d) => { if (d && !cancelled) setDemo(!!d.demo_mode); })
      .catch(() => {});
    return () => { cancelled = true; };
  }, []);

  return demo;
}

// ---------------------------------------------------------------------------
// Status → colour palette
// ---------------------------------------------------------------------------

function pipelineColors(status: PipelineStatus, active: boolean) {
  const s = status?.status ?? "idle";

  if (s === "failed") {
    return {
      bg:     active ? "rgba(234,67,53,0.22)" : "rgba(234,67,53,0.10)",
      border: active ? "rgba(234,67,53,0.55)" : "rgba(234,67,53,0.28)",
      icon:   "#ea4335",
      text:   "#f28b82",
      bar:    "#ea4335",
    };
  }
  if (s === "running") {
    return {
      bg:     active ? "rgba(52,168,83,0.25)" : "rgba(52,168,83,0.14)",
      border: active ? "rgba(52,168,83,0.55)" : "rgba(52,168,83,0.30)",
      icon:   "#34a853",
      text:   "#81c995",
      bar:    "#34a853",
    };
  }
  // idle / success / partial / cancelled → green
  return {
    bg:     active ? "rgba(52,168,83,0.22)" : "rgba(52,168,83,0.10)",
    border: active ? "rgba(52,168,83,0.50)" : "rgba(52,168,83,0.25)",
    icon:   "#34a853",
    text:   "#81c995",
    bar:    "#34a853",
  };
}

// ---------------------------------------------------------------------------
// Pipeline nav button - live status-aware
// ---------------------------------------------------------------------------

function PipelineNavButton({ item, active, pipelineStatus }: {
  item: NavItem;
  active: boolean;
  pipelineStatus: PipelineStatus;
}) {
  const c = pipelineColors(pipelineStatus, active);
  const isRunning = pipelineStatus?.status === "running";
  const progress  = pipelineStatus?.progress ?? 0;
  const stagesDone  = pipelineStatus?.stagesDone ?? 0;
  const stagesTotal = pipelineStatus?.stagesTotal ?? 0;

  const tooltipTitle = isRunning
    ? `Running · stage ${stagesDone}/${stagesTotal}`
    : pipelineStatus?.status === "failed"
    ? "Last run failed"
    : pipelineStatus?.status
    ? `Last run: ${pipelineStatus.status}`
    : "No recent run";

  return (
    <Tooltip title={tooltipTitle} placement="right" arrow>
      <ListItem disablePadding sx={{ mb: 0.25 }}>
        <ListItemButton
          component={Link}
          href={item.href}
          selected={active}
          sx={{
            borderRadius: 1.5,
            py: 0.75,
            position: "relative",
            overflow: "hidden",
            bgcolor: c.bg,
            border: "1px solid",
            borderColor: c.border,
            "&:hover": { bgcolor: c.bg, filter: "brightness(1.15)" },
            // Disable default MUI selected style - we manage it ourselves
            "&.Mui-selected": { bgcolor: c.bg },
            "&.Mui-selected:hover": { bgcolor: c.bg, filter: "brightness(1.15)" },
          }}
        >
          {/* Icon */}
          <ListItemIcon sx={{ minWidth: 32, color: c.icon }}>
            {isRunning ? (
              // Subtle pulse on the icon when running
              <Box sx={{ animation: "pulse 2s ease-in-out infinite", "@keyframes pulse": { "0%,100%": { opacity: 1 }, "50%": { opacity: 0.55 } } }}>
                {item.icon}
              </Box>
            ) : item.icon}
          </ListItemIcon>

          {/* Label + optional stage counter */}
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="body2" sx={{ fontWeight: 600, color: c.text, lineHeight: isRunning ? 1.1 : 1.4, display: "block" }}>
              {item.label}
            </Typography>
            {isRunning && (
              <Typography variant="caption" sx={{ color: c.icon, fontSize: "0.6rem", lineHeight: 1, opacity: 0.85, display: "block" }}>
                Stage {stagesDone}/{stagesTotal}
              </Typography>
            )}
          </Box>

          {/* Progress bar - pinned to bottom edge */}
          {isRunning && (
            <Box
              sx={{
                position: "absolute",
                bottom: 0,
                left: 0,
                right: 0,
                height: 3,
                bgcolor: "rgba(0,0,0,0.25)",
              }}
            >
              <Box
                sx={{
                  height: "100%",
                  width: `${progress}%`,
                  bgcolor: c.bar,
                  borderRadius: "0 2px 2px 0",
                  transition: "width 0.6s ease",
                  boxShadow: `0 0 6px ${c.bar}99`,
                }}
              />
            </Box>
          )}
        </ListItemButton>
      </ListItem>
    </Tooltip>
  );
}

// ---------------------------------------------------------------------------
// Standard nav button
// ---------------------------------------------------------------------------

function NavButton({ item, active }: { item: NavItem; active: boolean }) {
  return (
    <ListItem disablePadding sx={{ mb: 0.25 }}>
      <ListItemButton
        component={Link}
        href={item.href}
        selected={active}
        sx={{
          borderRadius: 1.5,
          py: 0.75,
          "&.Mui-selected": {
            bgcolor: "rgba(26,115,232,0.15)",
            "& .MuiListItemIcon-root": { color: "primary.light" },
          },
          "&.Mui-selected:hover": { bgcolor: "rgba(26,115,232,0.2)" },
          "&:hover": { bgcolor: "rgba(255,255,255,0.04)" },
        }}
      >
        <ListItemIcon sx={{ minWidth: 32, color: active ? "primary.light" : "text.secondary" }}>
          {item.icon}
        </ListItemIcon>
        <Typography
          variant="body2"
          sx={{ fontWeight: active ? 600 : 400, color: active ? "primary.light" : "text.secondary" }}
        >
          {item.label}
        </Typography>
      </ListItemButton>
    </ListItem>
  );
}

// ---------------------------------------------------------------------------
// Sidebar
// ---------------------------------------------------------------------------

export default function Sidebar() {
  const pathname = usePathname();
  const pipelineStatus = usePipelineStatus();
  const demoMode = useDemoMode();

  function isActive(href: string) {
    return pathname === href || (pathname === "/" && href === "/pipeline");
  }

  return (
    <Box
      sx={{
        width: 220,
        minHeight: "100vh",
        bgcolor: "#161b22",
        borderRight: "1px solid rgba(255,255,255,0.08)",
        display: "flex",
        flexDirection: "column",
        position: "fixed",
        top: 0,
        left: 0,
        bottom: 0,
        zIndex: 200,
        overflowY: "auto",
      }}
    >
      {/* Branding */}
      <Box sx={{ px: 2.5, py: 2, display: "flex", alignItems: "center", gap: 1.5 }}>
        <HubOutlinedIcon sx={{ color: "primary.main", fontSize: 22, flexShrink: 0 }} />
        <Box>
          <Typography variant="subtitle2" color="text.primary" sx={{ fontWeight: 700, letterSpacing: -0.3, lineHeight: 1.2 }}>
            Mycelium
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1 }}>
            Continuity Engine
          </Typography>
        </Box>
      </Box>

      <Divider sx={{ borderColor: "rgba(255,255,255,0.08)" }} />

      {/* Grouped navigation */}
      <Box sx={{ flex: 1, px: 1, py: 1.5, display: "flex", flexDirection: "column", gap: 0.5 }}>
        {NAV_GROUPS.map((group, gi) => (
          <Box key={group.section}>
            {gi > 0 && <Box sx={{ height: 4 }} />}
            <Typography
              sx={{
                px: 1.5,
                pb: 0.5,
                fontSize: "0.62rem",
                fontWeight: 700,
                letterSpacing: "0.1em",
                textTransform: "uppercase",
                color: "rgba(255,255,255,0.28)",
                userSelect: "none",
              }}
            >
              {group.section}
            </Typography>
            <List disablePadding>
              {group.items.map((item) =>
                item.primary ? (
                  <PipelineNavButton
                    key={item.href}
                    item={item}
                    active={isActive(item.href)}
                    pipelineStatus={pipelineStatus}
                  />
                ) : (
                  <NavButton key={item.href} item={item} active={isActive(item.href)} />
                )
              )}
            </List>
          </Box>
        ))}
      </Box>

      <Divider sx={{ borderColor: "rgba(255,255,255,0.08)" }} />

      {/* Configuration pinned at bottom */}
      <Box sx={{ px: 1, pt: 1 }}>
        <List disablePadding>
          <NavButton item={BOTTOM_ITEM} active={isActive(BOTTOM_ITEM.href)} />
        </List>
      </Box>

      {/* Connection status + demo mode indicator */}
      <Box sx={{ px: 2, py: 2 }}>
        <Typography
          variant="caption"
          color="text.disabled"
          sx={{ display: "block", mb: 1, textTransform: "uppercase", letterSpacing: "0.08em", fontSize: "0.65rem" }}
        >
          Connected
        </Typography>
        <Stack spacing={0.75}>
          {([
            { label: "Gemini",      dot: "#34a853", color: "primary.light",  border: "primary.dark" },
            { label: "GitLab MCP",  dot: "#34a853", color: "success.light",  border: "success.dark" },
            { label: "MongoDB MCP", dot: "#34a853", color: "warning.light",  border: "warning.dark" },
          ] as const).map(({ label, dot, color, border }) => (
            <Chip
              key={label}
              label={
                <Stack direction="row" spacing={0.75} sx={{ alignItems: "center" }}>
                  <Box sx={{ width: 7, height: 7, borderRadius: "50%", bgcolor: dot, flexShrink: 0, boxShadow: `0 0 4px ${dot}99` }} />
                  <span>{label}</span>
                </Stack>
              }
              size="small"
              variant="outlined"
              sx={{
                height: 20,
                fontSize: "0.68rem",
                color,
                borderColor: border,
                justifyContent: "flex-start",
                "& .MuiChip-label": { display: "flex", alignItems: "center", px: 1 },
              }}
            />
          ))}

          {/* Demo mode pill — only visible when DEMO_MODE=true on the backend */}
          {demoMode && (
            <Chip
              icon={<ScienceOutlinedIcon sx={{ fontSize: "13px !important", color: "#a78bfa !important" }} />}
              label="Demo mode"
              size="small"
              variant="outlined"
              sx={{
                height: 20,
                fontSize: "0.68rem",
                color: "#a78bfa",
                borderColor: "#7c3aed",
                justifyContent: "flex-start",
                "& .MuiChip-label": { display: "flex", alignItems: "center", px: 1 },
              }}
            />
          )}
        </Stack>
      </Box>
    </Box>
  );
}
