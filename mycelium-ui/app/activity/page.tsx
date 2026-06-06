// Copyright 2026 Javier Huang
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import Box from "@mui/material/Box";
import Typography from "@mui/material/Typography";
import ActivityFeed from "../components/ActivityFeed";

export default function ActivityPage() {
  return (
    <Box sx={{ px: 3, py: 3, bgcolor: "background.default", minHeight: "100vh" }}>
      <Box sx={{ mb: 3 }}>
        <Typography variant="h6" sx={{ fontWeight: 600 }} color="text.primary">
          Activity
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Live agent trace: thinking, tool calls, and subagent deployments
        </Typography>
      </Box>

      <ActivityFeed height="calc(100vh - 140px)" />
    </Box>
  );
}
