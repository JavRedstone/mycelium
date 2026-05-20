"use client";

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
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import TerminalOutlinedIcon from "@mui/icons-material/TerminalOutlined";
import TimelineOutlinedIcon from "@mui/icons-material/TimelineOutlined";

type NavItem = { label: string; href: string; icon: React.ReactNode };

const NAV_GROUPS: { section: string; items: NavItem[] }[] = [
  {
    section: "Repository",
    items: [
      { label: "Repository",      href: "/repo",    icon: <FolderOutlinedIcon fontSize="small" /> },
      { label: "Repo History",    href: "/history", icon: <HistoryOutlinedIcon fontSize="small" /> },
      { label: "Knowledge Graph", href: "/graph",   icon: <AccountTreeOutlinedIcon fontSize="small" /> },
    ],
  },
  {
    section: "Pipeline",
    items: [
      { label: "Pipeline",       href: "/pipeline",  icon: <PlayArrowOutlinedIcon fontSize="small" /> },
      { label: "Agent Activity", href: "/activity",  icon: <ChatOutlinedIcon fontSize="small" /> },
      { label: "Logs",           href: "/logs",      icon: <TerminalOutlinedIcon fontSize="small" /> },
      { label: "Actions",        href: "/actions",   icon: <BoltOutlinedIcon fontSize="small" /> },
    ],
  },
  {
    section: "Insights",
    items: [
      { label: "Timeline",        href: "/timeline",       icon: <TimelineOutlinedIcon fontSize="small" /> },
      { label: "Investigations",  href: "/investigations", icon: <BiotechOutlinedIcon fontSize="small" /> },
      { label: "Analytics",       href: "/analytics",      icon: <BarChartOutlinedIcon fontSize="small" /> },
    ],
  },
];

const BOTTOM_ITEM: NavItem = {
  label: "Configuration",
  href: "/config",
  icon: <SettingsOutlinedIcon fontSize="small" />,
};

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

export default function Sidebar() {
  const pathname = usePathname();

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
              {group.items.map((item) => (
                <NavButton key={item.href} item={item} active={isActive(item.href)} />
              ))}
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

      {/* Connection status */}
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
        </Stack>
      </Box>
    </Box>
  );
}
