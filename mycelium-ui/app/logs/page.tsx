import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import AgentLog from "../components/AgentLog";

export default function LogsPage() {
  return (
    <Box sx={{ px: 3, py: 3, bgcolor: "background.default", minHeight: "100vh" }}>
      <Stack spacing={3}>
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 600 }} color="text.primary">
            Agent Logs
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Live stream from the Mycelium continuity agent
          </Typography>
        </Box>

        <AgentLog height={700} />
      </Stack>
    </Box>
  );
}
