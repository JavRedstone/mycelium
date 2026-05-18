import Box from "@mui/material/Box";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import KnowledgeGraph from "../components/KnowledgeGraph";

export default function GraphPage() {
  return (
    <Box sx={{ px: 3, py: 3, bgcolor: "background.default", minHeight: "100vh" }}>
      <Stack spacing={3}>
        <Box>
          <Typography variant="h6" sx={{ fontWeight: 600 }} color="text.primary">
            Knowledge Graph
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Engineer expertise and module dependency map
          </Typography>
        </Box>

        <KnowledgeGraph />
      </Stack>
    </Box>
  );
}
