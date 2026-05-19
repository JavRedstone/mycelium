import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import RepoHistory from "../components/RepoHistory";

export default function HistoryPage() {
  return (
    <Box sx={{ px: 3, py: 3, bgcolor: "background.default", minHeight: "100vh" }}>
      <Stack spacing={3}>
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 600 }} color="text.primary">
            Repository History
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Contributor activity and module health over time, derived from the knowledge graph
          </Typography>
        </Box>

        <RepoHistory />
      </Stack>
    </Box>
  );
}
