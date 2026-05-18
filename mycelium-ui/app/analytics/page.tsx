import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Analytics from "../components/Analytics";

export default function AnalyticsPage() {
  return (
    <Box sx={{ px: 3, py: 3, bgcolor: "background.default", minHeight: "100vh" }}>
      <Stack spacing={3}>
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 600 }} color="text.primary">
            Analytics
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Risk distribution, bus factor breakdown, and developer expertise load
          </Typography>
        </Box>

        <Analytics />
      </Stack>
    </Box>
  );
}
