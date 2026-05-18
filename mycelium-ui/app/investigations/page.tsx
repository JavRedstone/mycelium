import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Investigations from "../components/Investigations";

export default function InvestigationsPage() {
  return (
    <Box sx={{ px: 3, py: 3, bgcolor: "background.default", minHeight: "100vh" }}>
      <Stack spacing={3}>
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 600 }} color="text.primary">
            Investigations
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Subagent findings — what the investigators read and judged. No thresholds, no formulas.
          </Typography>
        </Box>
        <Investigations />
      </Stack>
    </Box>
  );
}
