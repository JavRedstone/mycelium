"use client";

import { useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import Md from "./Md";

export type TraceEvent =
  | { type: "agent_text"; text: string }
  | { type: "tool_call"; tool: string; args: Record<string, unknown> }
  | { type: "tool_response"; tool: string; result: unknown };

// ---------------------------------------------------------------------------
// Agent reasoning bubble
// ---------------------------------------------------------------------------
function AgentBubble({ text }: { text: string }) {
  return (
    <Stack direction="row" spacing={1.5} sx={{ alignItems: "flex-start" }}>
      <Box sx={{ mt: 0.5, flexShrink: 0 }}>
        <SmartToyOutlinedIcon sx={{ fontSize: 15, color: "primary.light", opacity: 0.8 }} />
      </Box>
      <Box
        sx={{
          flex: 1,
          bgcolor: "rgba(66,133,244,0.07)",
          border: "1px solid rgba(66,133,244,0.15)",
          borderRadius: "4px 12px 12px 12px",
          px: 1.75,
          py: 1.25,
        }}
      >
        <Md>{text}</Md>
      </Box>
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Tool call card  (→ tool_name  args preview, expandable)
// ---------------------------------------------------------------------------
function ToolCallCard({ tool, args }: { tool: string; args: Record<string, unknown> }) {
  const [open, setOpen] = useState(false);
  const keys = Object.keys(args);
  const preview = keys
    .slice(0, 2)
    .map((k) => {
      const v = JSON.stringify(args[k]);
      return `${k}=${v.length > 40 ? v.slice(0, 40) + "…" : v}`;
    })
    .join(", ");

  return (
    <Stack direction="row" spacing={1.5} sx={{ alignItems: "flex-start", pl: 3.5 }}>
      <Box sx={{ mt: 0.85, flexShrink: 0 }}>
        <ArrowForwardIcon sx={{ fontSize: 11, color: "primary.main" }} />
      </Box>
      <Paper
        elevation={0}
        sx={{
          flex: 1,
          border: "1px solid rgba(66,133,244,0.2)",
          bgcolor: "rgba(66,133,244,0.04)",
          borderRadius: 1.5,
          overflow: "hidden",
        }}
      >
        <Stack
          direction="row"
          spacing={1}
          sx={{ px: 1.5, py: 0.75, cursor: keys.length > 0 ? "pointer" : "default", alignItems: "center" }}
          onClick={() => keys.length > 0 && setOpen((o) => !o)}
        >
          <Chip
            label={tool}
            size="small"
            color="primary"
            variant="outlined"
            sx={{ fontFamily: "var(--font-google-sans-code)", height: 20, fontSize: "0.62rem" }}
          />
          {preview && (
            <Typography
              variant="caption"
              sx={{
                fontFamily: "var(--font-google-sans-code)",
                color: "text.disabled",
                flex: 1,
                overflow: "hidden",
                textOverflow: "ellipsis",
                whiteSpace: "nowrap",
                fontSize: "0.68rem",
              }}
            >
              {preview}
            </Typography>
          )}
          {keys.length > 0 && (
            <ExpandMoreIcon
              sx={{
                fontSize: 14,
                color: "text.disabled",
                flexShrink: 0,
                transform: open ? "rotate(180deg)" : "none",
                transition: "transform 0.15s",
              }}
            />
          )}
        </Stack>
        {keys.length > 0 && (
          <Collapse in={open}>
            <Box
              sx={{
                px: 1.5,
                pb: 1.25,
                pt: 0.5,
                borderTop: "1px solid rgba(255,255,255,0.05)",
              }}
            >
              <Box
                component="pre"
                sx={{
                  m: 0,
                  fontSize: "0.68rem",
                  color: "text.secondary",
                  fontFamily: "var(--font-google-sans-code)",
                  overflow: "auto",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  maxHeight: 300,
                }}
              >
                {JSON.stringify(args, null, 2)}
              </Box>
            </Box>
          </Collapse>
        )}
      </Paper>
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Tool response card  (← tool_name  result preview, expandable)
// ---------------------------------------------------------------------------
function ToolResponseCard({ tool, result }: { tool: string; result: unknown }) {
  const [open, setOpen] = useState(false);
  const resultStr = result != null ? JSON.stringify(result) : "";
  const preview = resultStr.slice(0, 100) + (resultStr.length > 100 ? "…" : "");
  const hasDetail = resultStr.length > 100;

  // Extract a human-readable one-liner: prefer iid/web_url from create_issue results
  const r = result as Record<string, unknown> | null;
  const friendlyPreview = r?.iid
    ? `#${r.iid}${r.web_url ? " · " + String(r.web_url) : ""}`
    : preview;

  return (
    <Stack direction="row" spacing={1.5} sx={{ alignItems: "flex-start", pl: 3.5 }}>
      <Box sx={{ mt: 0.85, flexShrink: 0 }}>
        <ArrowBackIcon sx={{ fontSize: 11, color: "success.main" }} />
      </Box>
      <Paper
        elevation={0}
        sx={{
          flex: 1,
          border: "1px solid rgba(52,168,83,0.2)",
          bgcolor: "rgba(52,168,83,0.04)",
          borderRadius: 1.5,
          overflow: "hidden",
        }}
      >
        <Stack
          direction="row"
          spacing={1}
          sx={{ px: 1.5, py: 0.75, cursor: hasDetail ? "pointer" : "default", alignItems: "center" }}
          onClick={() => hasDetail && setOpen((o) => !o)}
        >
          <Typography
            variant="caption"
            sx={{
              fontFamily: "var(--font-google-sans-code)",
              color: "text.disabled",
              fontSize: "0.6rem",
              flexShrink: 0,
            }}
          >
            ← {tool}
          </Typography>
          <Typography
            variant="caption"
            sx={{
              fontFamily: "var(--font-google-sans-code)",
              color: "success.light",
              flex: 1,
              overflow: "hidden",
              textOverflow: "ellipsis",
              whiteSpace: "nowrap",
              fontSize: "0.68rem",
            }}
          >
            {friendlyPreview || "ok"}
          </Typography>
          {hasDetail && (
            <ExpandMoreIcon
              sx={{
                fontSize: 14,
                color: "text.disabled",
                flexShrink: 0,
                transform: open ? "rotate(180deg)" : "none",
                transition: "transform 0.15s",
              }}
            />
          )}
        </Stack>
        {hasDetail && (
          <Collapse in={open}>
            <Box sx={{ px: 1.5, pb: 1.25, pt: 0.5, borderTop: "1px solid rgba(255,255,255,0.05)" }}>
              <Box
                component="pre"
                sx={{
                  m: 0,
                  fontSize: "0.68rem",
                  color: "text.secondary",
                  fontFamily: "var(--font-google-sans-code)",
                  overflow: "auto",
                  whiteSpace: "pre-wrap",
                  wordBreak: "break-word",
                  maxHeight: 300,
                }}
              >
                {JSON.stringify(result, null, 2)}
              </Box>
            </Box>
          </Collapse>
        )}
      </Paper>
    </Stack>
  );
}

// ---------------------------------------------------------------------------
// Main export
// ---------------------------------------------------------------------------
export default function AgentTrace({ events }: { events: TraceEvent[] }) {
  const [collapsed, setCollapsed] = useState(false);
  if (!events || events.length === 0) return null;

  return (
    <Stack spacing={1}>
      <Stack
        direction="row"
        spacing={1}
        sx={{ alignItems: "center", cursor: "pointer", userSelect: "none" }}
        onClick={() => setCollapsed((c) => !c)}
      >
        <Typography
          variant="caption"
          color="text.disabled"
          sx={{ textTransform: "uppercase", letterSpacing: "0.08em", fontSize: "0.6rem" }}
        >
          Agent trace
        </Typography>
        <Chip
          label={events.length}
          size="small"
          variant="outlined"
          sx={{ height: 16, fontSize: "0.58rem", color: "text.disabled" }}
        />
        <ExpandMoreIcon
          sx={{
            fontSize: 14,
            color: "text.disabled",
            transform: collapsed ? "rotate(180deg)" : "none",
            transition: "transform 0.15s",
          }}
        />
      </Stack>

      <Collapse in={!collapsed}>
        <Stack spacing={0.75}>
          {events.map((event, i) => {
            if (event.type === "agent_text") {
              return <AgentBubble key={i} text={event.text} />;
            }
            if (event.type === "tool_call") {
              return <ToolCallCard key={i} tool={event.tool} args={event.args} />;
            }
            if (event.type === "tool_response") {
              return <ToolResponseCard key={i} tool={event.tool} result={event.result} />;
            }
            return null;
          })}
        </Stack>
      </Collapse>
    </Stack>
  );
}
