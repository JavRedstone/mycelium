import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ConfigPanel from "../components/ConfigPanel";

export default function ConfigPage() {
  return (
    <Box sx={{ px: 3, py: 3, bgcolor: "background.default", minHeight: "100vh" }}>
      <Stack spacing={3}>
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 600 }} color="text.primary">
            Configuration
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Runtime settings — edit via .env and restart the server to apply changes
          </Typography>
        </Box>

        <ConfigPanel />
      </Stack>
    </Box>
  );
}
