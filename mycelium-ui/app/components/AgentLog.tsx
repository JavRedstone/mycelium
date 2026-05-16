"use client";

import { useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import TerminalIcon from "@mui/icons-material/Terminal";

type LogEntry = {
  seq: number;
  ts: string;
  level: string;
  msg: string;
};

const LEVEL_COLOR: Record<string, string> = {
  DEBUG: "rgba(255,255,255,0.3)",
  INFO: "rgba(230,237,243,0.85)",
  WARNING: "#fbbc04",
  ERROR: "#ea4335",
  CRITICAL: "#ea4335",
};

const LEVEL_CHIP_COLOR: Record<string, "default" | "primary" | "warning" | "error"> = {
  DEBUG: "default",
  INFO: "primary",
  WARNING: "warning",
  ERROR: "error",
  CRITICAL: "error",
};

export default function AgentLog({ height = 320 }: { height?: number }) {
  const [entries, setEntries] = useState<LogEntry[]>([]);
  const [autoScroll, setAutoScroll] = useState(true);
  const bottomRef = useRef<HTMLDivElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  useEffect(() => {
    const es = new EventSource(`${apiUrl}/logs/stream`);
    es.onmessage = (e) => {
      try {
        const entry = JSON.parse(e.data) as LogEntry;
        setEntries((prev) => [...prev.slice(-499), entry]);
      } catch {}
    };
    return () => es.close();
  }, [apiUrl]);

  useEffect(() => {
    if (autoScroll) bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [entries, autoScroll]);

  function onScroll() {
    const el = containerRef.current;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 40;
    setAutoScroll(atBottom);
  }

  return (
    <Stack spacing={2}>
      <Stack direction="row" sx={{ justifyContent: "space-between", alignItems: "center" }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
          <Typography variant="subtitle2" color="text.secondary">
            Agent Log
          </Typography>
          <Typography variant="caption" color="text.disabled">
            {entries.length} entries
          </Typography>
        </Stack>
        {!autoScroll && (
          <Typography
            variant="caption"
            color="primary.main"
            sx={{ cursor: "pointer", userSelect: "none" }}
            onClick={() => {
              setAutoScroll(true);
              bottomRef.current?.scrollIntoView({ behavior: "smooth" });
            }}
          >
            ↓ Scroll to bottom
          </Typography>
        )}
      </Stack>

      <Paper elevation={0} sx={{ height, overflow: "hidden", display: "flex", flexDirection: "column" }}>
        {/* Terminal header bar */}
        <Box sx={{ px: 2, py: 1, borderBottom: "1px solid rgba(255,255,255,0.06)", display: "flex", alignItems: "center", gap: 1, bgcolor: "rgba(255,255,255,0.02)" }}>
          <TerminalIcon sx={{ fontSize: 14, color: "text.disabled" }} />
          <Typography variant="caption" color="text.disabled" sx={{ fontFamily: "var(--font-google-sans-code)" }}>
            mycelium — continuity engine
          </Typography>
        </Box>

        {/* Log lines */}
        <Box
          ref={containerRef}
          onScroll={onScroll}
          sx={{
            flex: 1,
            overflowY: "auto",
            p: 1.5,
            "&::-webkit-scrollbar": { width: 4 },
            "&::-webkit-scrollbar-track": { bgcolor: "transparent" },
            "&::-webkit-scrollbar-thumb": { bgcolor: "rgba(255,255,255,0.1)", borderRadius: 2 },
          }}
        >
          {entries.length === 0 ? (
            <Typography variant="caption" color="text.disabled" sx={{ fontFamily: "var(--font-google-sans-code)" }}>
              Waiting for logs…
            </Typography>
          ) : (
            entries.map((entry) => (
              <Stack key={entry.seq} direction="row" spacing={1.5} sx={{ alignItems: "baseline", mb: 0.25 }}>
                <Typography component="span" sx={{ fontFamily: "var(--font-google-sans-code)", fontSize: "0.7rem", color: "rgba(255,255,255,0.25)", flexShrink: 0, minWidth: 56 }}>
                  {entry.ts}
                </Typography>
                <Box sx={{ flexShrink: 0 }}>
                  <Chip
                    label={entry.level}
                    size="small"
                    color={LEVEL_CHIP_COLOR[entry.level] ?? "default"}
                    variant="outlined"
                    sx={{ height: 16, fontSize: "0.6rem", fontFamily: "var(--font-google-sans-code)", "& .MuiChip-label": { px: 0.75 } }}
                  />
                </Box>
                <Typography component="span" sx={{ fontFamily: "var(--font-google-sans-code)", fontSize: "0.75rem", color: LEVEL_COLOR[entry.level] ?? "rgba(255,255,255,0.7)", wordBreak: "break-word" }}>
                  {entry.msg}
                </Typography>
              </Stack>
            ))
          )}
          <div ref={bottomRef} />
        </Box>
      </Paper>
    </Stack>
  );
}
