import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import ActivityFeed from "../components/ActivityFeed";

export default function ActivityPage() {
  return (
    <Box sx={{ px: 3, py: 3, bgcolor: "background.default", minHeight: "100vh" }}>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h6" sx={{ fontWeight: 600 }} color="text.primary">
          Activity
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Live agent trace — thinking, tool calls, and subagent deployments
        </Typography>
      </Box>

      <ActivityFeed height="calc(100vh - 140px)" />
    </Box>
  );
}
