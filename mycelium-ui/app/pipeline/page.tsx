import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ActivityFeed from "../components/ActivityFeed";
import AgentLog from "../components/AgentLog";
import Pipeline from "../components/Pipeline";
import RunHistory from "../components/RunHistory";

export default function PipelinePage() {
  return (
    <Box sx={{ px: 3, py: 3, bgcolor: "background.default", minHeight: "100vh" }}>
      <Stack spacing={3}>
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 600 }} color="text.primary">
            Pipeline
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Real-time agent execution and run history
          </Typography>
        </Box>

        <RunHistory />

        {/* Top row: stage list + logs panel */}
        <Box
          sx={{
            display: "grid",
            gridTemplateColumns: { xs: "1fr", lg: "minmax(0, 1fr) 380px" },
            gap: 3,
            alignItems: "start",
          }}
        >
          <Pipeline />
          <Box sx={{ position: "sticky", top: 24 }}>
            <AgentLog height={520} />
          </Box>
        </Box>

        {/* Bottom: agent activity feed - full width */}
        <ActivityFeed height={520} />
      </Stack>
    </Box>
  );
}
