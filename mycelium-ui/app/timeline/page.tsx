import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Timeline from "../components/Timeline";

export default function TimelinePage() {
  return (
    <Box sx={{ px: 3, py: 3, bgcolor: "background.default", minHeight: "100vh" }}>
      <Stack spacing={3}>
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 600 }} color="text.primary">
            Timeline
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Chronological history of pipeline runs, findings detected, and actions taken in GitLab
          </Typography>
        </Box>

        <Timeline />
      </Stack>
    </Box>
  );
}
