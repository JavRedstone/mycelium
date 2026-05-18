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
import HubOutlinedIcon from "@mui/icons-material/HubOutlined";
import PlayArrowOutlinedIcon from "@mui/icons-material/PlayArrowOutlined";
import SettingsOutlinedIcon from "@mui/icons-material/SettingsOutlined";
import TerminalOutlinedIcon from "@mui/icons-material/TerminalOutlined";

const NAV_ITEMS = [
  { label: "Pipeline", href: "/pipeline", icon: <PlayArrowOutlinedIcon fontSize="small" /> },
  { label: "Knowledge Graph", href: "/graph", icon: <AccountTreeOutlinedIcon fontSize="small" /> },
  { label: "Investigations", href: "/investigations", icon: <BiotechOutlinedIcon fontSize="small" /> },
  { label: "Analytics", href: "/analytics", icon: <BarChartOutlinedIcon fontSize="small" /> },
  { label: "Actions", href: "/actions", icon: <BoltOutlinedIcon fontSize="small" /> },
  { label: "Logs", href: "/logs", icon: <TerminalOutlinedIcon fontSize="small" /> },
  { label: "Configuration", href: "/config", icon: <SettingsOutlinedIcon fontSize="small" /> },
];

export default function Sidebar() {
  const pathname = usePathname();

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
          <Typography
            variant="subtitle2"
            color="text.primary"
            sx={{ fontWeight: 700, letterSpacing: -0.3, lineHeight: 1.2 }}
          >
            Mycelium
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1 }}>
            Continuity Engine
          </Typography>
        </Box>
      </Box>

      <Divider sx={{ borderColor: "rgba(255,255,255,0.08)" }} />

      {/* Navigation */}
      <List sx={{ px: 1, py: 1.5, flex: 1 }} disablePadding>
        {NAV_ITEMS.map((item) => {
          const active =
            pathname === item.href ||
            (pathname === "/" && item.href === "/pipeline");
          return (
            <ListItem key={item.href} disablePadding sx={{ mb: 0.25 }}>
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
                  "&.Mui-selected:hover": {
                    bgcolor: "rgba(26,115,232,0.2)",
                  },
                  "&:hover": { bgcolor: "rgba(255,255,255,0.04)" },
                }}
              >
                <ListItemIcon
                  sx={{
                    minWidth: 32,
                    color: active ? "primary.light" : "text.secondary",
                  }}
                >
                  {item.icon}
                </ListItemIcon>
                <Typography
                  variant="body2"
                  sx={{
                    fontWeight: active ? 600 : 400,
                    color: active ? "primary.light" : "text.secondary",
                  }}
                >
                  {item.label}
                </Typography>
              </ListItemButton>
            </ListItem>
          );
        })}
      </List>

      <Divider sx={{ borderColor: "rgba(255,255,255,0.08)" }} />

      {/* Connection status */}
      <Box sx={{ px: 2, py: 2 }}>
        <Typography
          variant="caption"
          color="text.disabled"
          sx={{
            display: "block",
            mb: 1,
            textTransform: "uppercase",
            letterSpacing: "0.08em",
            fontSize: "0.65rem",
          }}
        >
          Connected
        </Typography>
        <Stack spacing={0.75}>
          <Chip
            label="Gemini"
            size="small"
            variant="outlined"
            sx={{
              height: 20,
              fontSize: "0.68rem",
              color: "primary.light",
              borderColor: "primary.dark",
              justifyContent: "flex-start",
            }}
          />
          <Chip
            label="GitLab MCP"
            size="small"
            variant="outlined"
            sx={{
              height: 20,
              fontSize: "0.68rem",
              color: "success.light",
              borderColor: "success.dark",
              justifyContent: "flex-start",
            }}
          />
          <Chip
            label="MongoDB MCP"
            size="small"
            variant="outlined"
            sx={{
              height: 20,
              fontSize: "0.68rem",
              color: "warning.light",
              borderColor: "warning.dark",
              justifyContent: "flex-start",
            }}
          />
        </Stack>
      </Box>
    </Box>
  );
}
