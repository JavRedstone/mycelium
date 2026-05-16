import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Divider from "@mui/material/Divider";
import Chip from "@mui/material/Chip";
import HubOutlinedIcon from "@mui/icons-material/HubOutlined";
import Pipeline from "./components/Pipeline";
import RunHistory from "./components/RunHistory";
import AgentLog from "./components/AgentLog";
import KnowledgeGraph from "./components/KnowledgeGraph";

export default function Page() {
  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      {/* Sticky header */}
      <Box
        component="header"
        sx={{
          px: 3,
          py: 1.5,
          borderBottom: "1px solid rgba(255,255,255,0.08)",
          bgcolor: "#161b22",
          display: "flex",
          alignItems: "center",
          gap: 2,
          position: "sticky",
          top: 0,
          zIndex: 100,
        }}
      >
        <Stack direction="row" spacing={1.5} sx={{ alignItems: "center" }}>
          <HubOutlinedIcon sx={{ color: "primary.main", fontSize: 22 }} />
          <Typography variant="subtitle1" color="text.primary" sx={{ fontWeight: 600, letterSpacing: -0.3 }}>
            Mycelium
          </Typography>
          <Divider orientation="vertical" flexItem sx={{ mx: 0.5, borderColor: "rgba(255,255,255,0.1)" }} />
          <Typography variant="body2" color="text.secondary">
            Continuity Engine
          </Typography>
        </Stack>
        <Box sx={{ flex: 1 }} />
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
          <Chip label="Gemini" size="small" variant="outlined" sx={{ height: 22, fontSize: "0.7rem", color: "primary.light", borderColor: "primary.dark" }} />
          <Chip label="GitLab MCP" size="small" variant="outlined" sx={{ height: 22, fontSize: "0.7rem", color: "success.light", borderColor: "success.dark" }} />
          <Chip label="MongoDB" size="small" variant="outlined" sx={{ height: 22, fontSize: "0.7rem", color: "warning.light", borderColor: "warning.dark" }} />
        </Stack>
      </Box>

      <Box component="main" sx={{ maxWidth: 1400, mx: "auto", px: 3, py: 4 }}>
        <Stack spacing={4}>
          {/* Top: run history timeline — full width, horizontal scrollable */}
          <RunHistory />

          {/* Middle: current run (vertical stages, left) + console (right) */}
          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: "1fr 400px",
              gap: 3,
              alignItems: "start",
            }}
          >
            <Pipeline />
            <Box sx={{ position: "sticky", top: 72 }}>
              <AgentLog height={560} />
            </Box>
          </Box>

          {/* Bottom: knowledge graph */}
          <KnowledgeGraph />
        </Stack>
      </Box>
    </Box>
  );
}
