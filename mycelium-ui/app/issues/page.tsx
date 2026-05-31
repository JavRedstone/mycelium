import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Issues from "../components/Issues";

export default function IssuesPage() {
  return (
    <Box sx={{ px: 3, py: 3, bgcolor: "background.default", minHeight: "100vh" }}>
      <Stack spacing={3}>
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 600 }} color="text.primary">
            Open Issues
          </Typography>
          <Typography variant="body2" color="text.secondary">
            GitLab issues created or labelled by the Mycelium continuity engine
          </Typography>
        </Box>
        <Issues />
      </Stack>
    </Box>
  );
}
