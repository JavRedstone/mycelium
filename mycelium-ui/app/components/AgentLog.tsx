"use client";

import { useEffect, useRef, useState } from "react";
import Box from "@mui/material/Box";
import IconButton from "@mui/material/IconButton";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";
import Chip from "@mui/material/Chip";
import Divider from "@mui/material/Divider";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import TerminalIcon from "@mui/icons-material/Terminal";
import { scrollbarSx } from "../lib/sx";

type LogEntry = {
  seq: number;
  ts: string;
  level: string;
  msg: string;
};

type LogEntryKeyed = LogEntry & { _clientKey: number };

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
  const [entries, setEntries] = useState<LogEntryKeyed[]>([]);
  const containerRef = useRef<HTMLDivElement>(null);
  const keyRef = useRef(0);
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  useEffect(() => {
    const es = new EventSource(`${apiUrl}/logs/stream`);
    es.onopen = () => {
      keyRef.current = 0;
      setEntries([]);
    };
    es.onmessage = (e) => {
      try {
        const entry = JSON.parse(e.data) as LogEntry;
        const _clientKey = keyRef.current++;
        setEntries((prev) => [...prev.slice(-499), { ...entry, _clientKey }]);
      } catch {}
    };
    return () => es.close();
  }, [apiUrl]);

  function scrollToBottom() {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
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
        <Tooltip title="Scroll to latest" placement="left" arrow>
          <IconButton size="small" onClick={scrollToBottom} sx={{ p: 0.5, color: "primary.main" }}>
            <KeyboardArrowDownIcon sx={{ fontSize: 16 }} />
          </IconButton>
        </Tooltip>
      </Stack>

      <Paper elevation={0} sx={{ height, overflow: "hidden", display: "flex", flexDirection: "column" }}>
        {/* Terminal header bar */}
        <Box sx={{ px: 2, py: 1, borderBottom: "1px solid rgba(255,255,255,0.06)", display: "flex", alignItems: "center", gap: 1, bgcolor: "rgba(255,255,255,0.02)" }}>
          <TerminalIcon sx={{ fontSize: 14, color: "text.disabled" }} />
          <Typography variant="caption" color="text.disabled" sx={{ fontFamily: "var(--font-google-sans-code)" }}>
            mycelium · continuity engine
          </Typography>
        </Box>

        {/* Log lines */}
        <Box
          ref={containerRef}
          sx={{ flex: 1, overflowY: "auto", p: 1.5, ...scrollbarSx }}
        >
          {entries.length === 0 ? (
            <Typography variant="caption" color="text.disabled" sx={{ fontFamily: "var(--font-google-sans-code)" }}>
              Waiting for logs…
            </Typography>
          ) : (
            entries.map((entry, idx) => {
              const isRunStart = entry.msg.includes("[pipeline] Observe Repo started");
              const isFirstEntry = idx === 0;
              return (
                <Box key={entry._clientKey}>
                  {isRunStart && !isFirstEntry && (
                    <Box sx={{ my: 1.5 }}>
                      <Divider sx={{ borderColor: "rgba(255,255,255,0.12)" }}>
                        <Typography variant="caption" sx={{ fontFamily: "var(--font-google-sans-code)", fontSize: "0.65rem", color: "rgba(255,255,255,0.3)", px: 1 }}>
                          ── new run · {entry.ts} ──
                        </Typography>
                      </Divider>
                    </Box>
                  )}
                  <Stack direction="row" spacing={1.5} sx={{ alignItems: "baseline", mb: 0.25 }}>
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
                </Box>
              );
            })
          )}
        </Box>
      </Paper>
    </Stack>
  );
}
