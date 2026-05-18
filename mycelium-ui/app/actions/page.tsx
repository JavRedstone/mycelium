import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Actions from "../components/Actions";

export default function ActionsPage() {
  return (
    <Box sx={{ px: 3, py: 3, bgcolor: "background.default", minHeight: "100vh" }}>
      <Stack spacing={3}>
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 600 }} color="text.primary">
            Actions
          </Typography>
          <Typography variant="body2" color="text.secondary">
            What the agent has done to remediate continuity risks
          </Typography>
        </Box>
        <Actions />
      </Stack>
    </Box>
  );
}
