import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import MockRepo from "../components/MockRepo";

export default function RepoPage() {
  return (
    <Box sx={{ px: 3, py: 3, bgcolor: "background.default", minHeight: "100vh" }}>
      <Stack spacing={3}>
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 600 }} color="text.primary">
            Repository
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Knowledge graph state as a repository file browser — who owns what,
            when they last committed, and where coverage is at risk
          </Typography>
        </Box>

        <MockRepo />
      </Stack>
    </Box>
  );
}
