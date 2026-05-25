"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import Box from "@mui/material/Box";
import Chip from "@mui/material/Chip";
import Collapse from "@mui/material/Collapse";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import IconButton from "@mui/material/IconButton";
import AccountTreeOutlinedIcon from "@mui/icons-material/AccountTreeOutlined";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import BiotechOutlinedIcon from "@mui/icons-material/BiotechOutlined";
import BoltOutlinedIcon from "@mui/icons-material/BoltOutlined";
import CheckCircleOutlinedIcon from "@mui/icons-material/CheckCircleOutlined";
import ErrorOutlinedIcon from "@mui/icons-material/ErrorOutlined";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import FolderOutlinedIcon from "@mui/icons-material/FolderOutlined";
import PersonOutlinedIcon from "@mui/icons-material/PersonOutlined";
import PlayArrowOutlinedIcon from "@mui/icons-material/PlayArrowOutlined";
import SmartToyOutlinedIcon from "@mui/icons-material/SmartToyOutlined";
import SyncProblemOutlinedIcon from "@mui/icons-material/SyncProblemOutlined";
import WarningAmberOutlinedIcon from "@mui/icons-material/WarningAmberOutlined";
import Md from "./Md";
import { scrollbarSx } from "../lib/sx";

// ---------------------------------------------------------------------------
// Event types (mirroring activity_bus.py schema)
// ---------------------------------------------------------------------------
type RunStart       = { type: "run_start";       ts: number; run_id: string };
type RunEnd         = { type: "run_end";          ts: number; run_id: string; status: string };
type StageStart     = { type: "stage_start";      ts: number; stage_id: string; label: string };
type StageEnd       = { type: "stage_end";        ts: number; stage_id: string; label: string; status: string; duration_ms: number; error?: string };
type AgentText      = { type: "agent_text";       ts: number; stage_id: string; text: string };
type ToolCall       = { type: "tool_call";        ts: number; stage_id: string; tool: string; args: Record<string, unknown> };
type ToolResponse   = { type: "tool_response";    ts: number; stage_id: string; tool: string; result: unknown };
type SubagentSpawn  = { type: "subagent_spawn";   ts: number; stage_id: string; kind: string; subject: string; reason?: string };
type SubagentResult = { type: "subagent_result";  ts: number; stage_id: string; kind: string; subject: string; summary: string };
type Finding        = { type: "finding";          ts: number; stage_id: string; subject: string; concern_type: string; narrative: string };
type ActionPlanned  = { type: "action_planned";   ts: number; stage_id: string; kind: string; title: string };

type ActivityEvent =
  | RunStart | RunEnd | StageStart | StageEnd
  | AgentText | ToolCall | ToolResponse
  | SubagentSpawn | SubagentResult
  | Finding | ActionPlanned;

// (Stage order and labels are derived from live event data — no hardcoded list needed)

// ---------------------------------------------------------------------------
// Small display helpers
// ---------------------------------------------------------------------------
const CONCERN_COLORS: Record<string, string> = {
  sole_contributor:           "#ea4335",
  multi_module_concentration: "#fa7b17",
  upstream_dominance:         "#fbbc04",
  recently_inactive:          "#fbbc04",
  dark_knowledge:             "#fa7b17",
};
function concernColor(ct: string) { return CONCERN_COLORS[ct] ?? "#8ab4f8"; }

function fmtTs(ts: number) {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function fmtDuration(ms: number) {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`;
}

// ---------------------------------------------------------------------------
// Row wrappers
// ---------------------------------------------------------------------------
function Row({ indent = 0, children }: { indent?: number; children: React.ReactNode }) {
  return (
    <Box sx={{ pl: indent * 2.5, display: "flex", alignItems: "flex-start", gap: 1.25, py: 0.2 }}>
      {children}
    </Box>
  );
}

function Ts({ ts }: { ts: number }) {
  return (
    <Typography
      component="span"
      sx={{ fontFamily: "var(--font-google-sans-code)", fontSize: "0.6rem",
            color: "rgba(255,255,255,0.18)", flexShrink: 0, mt: "2px", minWidth: 54 }}
    >
      {fmtTs(ts)}
    </Typography>
  );
}

// ---------------------------------------------------------------------------
// Individual event renderers
// ---------------------------------------------------------------------------

function RunStartRow({ e }: { e: RunStart }) {
  return (
    <Box sx={{ my: 1.5 }}>
      <Divider sx={{ borderColor: "rgba(255,255,255,0.10)" }}>
        <Typography variant="caption"
          sx={{ fontFamily: "var(--font-google-sans-code)", fontSize: "0.6rem",
                color: "rgba(255,255,255,0.3)", px: 1 }}>
          ── new run · {fmtTs(e.ts)} ──
        </Typography>
      </Divider>
    </Box>
  );
}

function RunEndRow({ e }: { e: RunEnd }) {
  const ok = e.status === "success";
  const cancelled = e.status === "cancelled";
  const color = ok ? "success.main" : cancelled ? "warning.main" : "error.main";
  return (
    <Row>
      <Ts ts={e.ts} />
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
        {ok
          ? <CheckCircleOutlinedIcon sx={{ fontSize: 13, color }} />
          : <ErrorOutlinedIcon sx={{ fontSize: 13, color }} />}
        <Typography variant="caption" sx={{ color, fontWeight: 600, fontSize: "0.72rem" }}>
          Run {e.status}
        </Typography>
      </Box>
    </Row>
  );
}

function StageStartRow({ e }: { e: StageStart }) {
  const ICONS: Record<string, React.ReactElement> = {
    observe_repo: <PlayArrowOutlinedIcon sx={{ fontSize: 12 }} />,
    map_modules: <FolderOutlinedIcon sx={{ fontSize: 12 }} />,
    investigate: <BiotechOutlinedIcon sx={{ fontSize: 12 }} />,
    observe_graph: <AccountTreeOutlinedIcon sx={{ fontSize: 12 }} />,
    interpret: <BoltOutlinedIcon sx={{ fontSize: 12 }} />,
    plan: <AssignmentOutlinedIcon sx={{ fontSize: 12 }} />,
    act: <SmartToyOutlinedIcon sx={{ fontSize: 12 }} />,
  };
  return (
    <Row>
      <Ts ts={e.ts} />
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
        <Box sx={{ color: "primary.main", display: "flex" }}>
          {ICONS[e.stage_id] ?? <PlayArrowOutlinedIcon sx={{ fontSize: 12 }} />}
        </Box>
        <Typography variant="caption" sx={{ color: "primary.light", fontWeight: 600, fontSize: "0.7rem" }}>
          {e.label}
        </Typography>
        <Typography variant="caption" sx={{ color: "text.disabled", fontSize: "0.6rem" }}>
          started
        </Typography>
      </Box>
    </Row>
  );
}

function StageEndRow({ e }: { e: StageEnd }) {
  const ok = e.status === "success";
  return (
    <Row indent={1}>
      <Ts ts={e.ts} />
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
        {ok
          ? <CheckCircleOutlinedIcon sx={{ fontSize: 11, color: "success.main" }} />
          : <ErrorOutlinedIcon sx={{ fontSize: 11, color: "error.main" }} />}
        <Typography variant="caption"
          sx={{ color: ok ? "success.main" : "error.main", fontSize: "0.65rem" }}>
          {e.label}: {ok ? `done in ${fmtDuration(e.duration_ms)}` : `failed: ${e.error ?? "unknown"}`}
        </Typography>
      </Box>
    </Row>
  );
}

const AGENT_TEXT_COLLAPSE_LEN = 400;

function AgentTextRow({ e }: { e: AgentText }) {
  const [expanded, setExpanded] = useState(false);
  const isLong = e.text.length > AGENT_TEXT_COLLAPSE_LEN;
  const displayText = isLong && !expanded ? e.text.slice(0, AGENT_TEXT_COLLAPSE_LEN) + "…" : e.text;

  return (
    <Row indent={1}>
      <Ts ts={e.ts} />
      <Stack direction="row" spacing={1} sx={{ alignItems: "flex-start", flex: 1 }}>
        <SmartToyOutlinedIcon sx={{ fontSize: 13, color: "primary.light", opacity: 0.7, mt: "2px", flexShrink: 0 }} />
        <Box
          sx={{
            flex: 1,
            bgcolor: "rgba(66,133,244,0.06)",
            border: "1px solid rgba(66,133,244,0.12)",
            borderRadius: "3px 8px 8px 8px",
            px: 1.25,
            py: 0.75,
          }}
        >
          <Md compact>{displayText}</Md>
          {isLong && (
            <Typography
              variant="caption"
              onClick={() => setExpanded(x => !x)}
              sx={{ display: "block", mt: 0.5, cursor: "pointer", color: "primary.light",
                    fontSize: "0.6rem", userSelect: "none" }}
            >
              {expanded ? "▲ collapse" : `▼ show ${e.text.length - AGENT_TEXT_COLLAPSE_LEN} more chars`}
            </Typography>
          )}
        </Box>
      </Stack>
    </Row>
  );
}

function ToolCallRow({ e }: { e: ToolCall }) {
  const [open, setOpen] = useState(false);
  const keys = Object.keys(e.args);
  const preview = keys
    .slice(0, 2)
    .map((k) => {
      const v = JSON.stringify(e.args[k]);
      return `${k}=${v.length > 35 ? v.slice(0, 35) + "…" : v}`;
    })
    .join(", ");

  return (
    <Row indent={2}>
      <Ts ts={e.ts} />
      <ArrowForwardIcon sx={{ fontSize: 10, color: "primary.main", mt: "3px", flexShrink: 0 }} />
      <Paper elevation={0} sx={{ flex: 1, border: "1px solid rgba(66,133,244,0.18)",
          bgcolor: "rgba(66,133,244,0.04)", borderRadius: 1.5, overflow: "hidden" }}>
        <Stack direction="row" spacing={1} sx={{ px: 1.25, py: 0.5, alignItems: "center",
            cursor: keys.length > 0 ? "pointer" : "default" }}
          onClick={() => keys.length > 0 && setOpen(o => !o)}>
          <Chip label={e.tool} size="small" color="primary" variant="outlined"
            sx={{ fontFamily: "var(--font-google-sans-code)", height: 17, fontSize: "0.58rem" }} />
          {preview && (
            <Typography variant="caption"
              sx={{ fontFamily: "var(--font-google-sans-code)", color: "text.disabled",
                    flex: 1, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap",
                    fontSize: "0.62rem" }}>
              {preview}
            </Typography>
          )}
          {keys.length > 0 && (
            <ExpandMoreIcon sx={{ fontSize: 12, color: "text.disabled", flexShrink: 0,
                transform: open ? "rotate(180deg)" : "none", transition: "transform 0.12s" }} />
          )}
        </Stack>
        {keys.length > 0 && (
          <Collapse in={open}>
            <Box sx={{ px: 1.25, pb: 1, pt: 0.5, borderTop: "1px solid rgba(255,255,255,0.05)" }}>
              <Box component="pre" sx={{ m: 0, fontSize: "0.62rem", color: "text.secondary",
                  fontFamily: "var(--font-google-sans-code)", whiteSpace: "pre-wrap",
                  wordBreak: "break-word", maxHeight: 240, overflow: "auto", ...scrollbarSx }}>
                {JSON.stringify(e.args, null, 2)}
              </Box>
            </Box>
          </Collapse>
        )}
      </Paper>
    </Row>
  );
}

function ToolResponseRow({ e }: { e: ToolResponse }) {
  const [open, setOpen] = useState(false);
  const str = e.result != null ? JSON.stringify(e.result) : "";
  const r = e.result as Record<string, unknown> | null;
  const preview = r?.iid
    ? `#${r.iid}${r.web_url ? " · " + String(r.web_url) : ""}`
    : str.slice(0, 90) + (str.length > 90 ? "…" : "");

  return (
    <Row indent={2}>
      <Ts ts={e.ts} />
      <ArrowBackIcon sx={{ fontSize: 10, color: "success.main", mt: "3px", flexShrink: 0 }} />
      <Paper elevation={0} sx={{ flex: 1, border: "1px solid rgba(52,168,83,0.18)",
          bgcolor: "rgba(52,168,83,0.04)", borderRadius: 1.5, overflow: "hidden" }}>
        <Stack direction="row" spacing={1} sx={{ px: 1.25, py: 0.5, alignItems: "center",
            cursor: str.length > 90 ? "pointer" : "default" }}
          onClick={() => str.length > 90 && setOpen(o => !o)}>
          <Typography variant="caption" sx={{ fontFamily: "var(--font-google-sans-code)",
              color: "text.disabled", fontSize: "0.58rem", flexShrink: 0 }}>
            ← {e.tool}
          </Typography>
          <Typography variant="caption" sx={{ fontFamily: "var(--font-google-sans-code)",
              color: "success.light", flex: 1, overflow: "hidden", textOverflow: "ellipsis",
              whiteSpace: "nowrap", fontSize: "0.62rem" }}>
            {preview || "ok"}
          </Typography>
          {str.length > 90 && (
            <ExpandMoreIcon sx={{ fontSize: 12, color: "text.disabled", flexShrink: 0,
                transform: open ? "rotate(180deg)" : "none", transition: "transform 0.12s" }} />
          )}
        </Stack>
        {str.length > 90 && (
          <Collapse in={open}>
            <Box sx={{ px: 1.25, pb: 1, pt: 0.5, borderTop: "1px solid rgba(255,255,255,0.05)" }}>
              <Box component="pre" sx={{ m: 0, fontSize: "0.62rem", color: "text.secondary",
                  fontFamily: "var(--font-google-sans-code)", whiteSpace: "pre-wrap",
                  wordBreak: "break-word", maxHeight: 240, overflow: "auto", ...scrollbarSx }}>
                {JSON.stringify(e.result, null, 2)}
              </Box>
            </Box>
          </Collapse>
        )}
      </Paper>
    </Row>
  );
}

function SubagentSpawnRow({ e }: { e: SubagentSpawn }) {
  const icon =
    e.kind === "member" ? <PersonOutlinedIcon sx={{ fontSize: 11, color: "#fbbc04" }} /> :
    e.kind === "drift"  ? <SyncProblemOutlinedIcon sx={{ fontSize: 11, color: "#fbbc04" }} /> :
                          <FolderOutlinedIcon sx={{ fontSize: 11, color: "#8ab4f8" }} />;
  return (
    <Row indent={1}>
      <Ts ts={e.ts} />
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
        <BiotechOutlinedIcon sx={{ fontSize: 11, color: "text.disabled" }} />
        <Typography variant="caption" sx={{ color: "text.disabled", fontSize: "0.62rem" }}>
          spawning {e.kind} investigator
        </Typography>
        {icon}
        <Typography variant="caption"
          sx={{ fontFamily: "var(--font-google-sans-code)", color: "text.secondary", fontSize: "0.62rem" }}>
          {e.subject}
        </Typography>
        {e.reason && (
          <Chip label={e.reason.replace(/_/g, " ")} size="small" variant="outlined"
            sx={{ height: 15, fontSize: "0.55rem", color: "text.disabled" }} />
        )}
      </Box>
    </Row>
  );
}

function SubagentResultRow({ e }: { e: SubagentResult }) {
  const icon =
    e.kind === "member" ? <PersonOutlinedIcon sx={{ fontSize: 11, color: "success.main" }} /> :
    e.kind === "drift"  ? <SyncProblemOutlinedIcon sx={{ fontSize: 11, color: "success.main" }} /> :
                          <FolderOutlinedIcon sx={{ fontSize: 11, color: "success.main" }} />;
  return (
    <Row indent={2}>
      <Ts ts={e.ts} />
      <Box sx={{ display: "flex", alignItems: "flex-start", gap: 0.75, flex: 1 }}>
        <CheckCircleOutlinedIcon sx={{ fontSize: 10, color: "success.main", mt: "2px", flexShrink: 0 }} />
        {icon}
        <Box>
          <Typography component="span"
            sx={{ fontFamily: "var(--font-google-sans-code)", fontSize: "0.62rem",
                  color: "text.secondary", mr: 0.75 }}>
            {e.subject}
          </Typography>
          <Typography component="span" variant="caption" sx={{ color: "text.disabled", fontSize: "0.62rem" }}>
            {e.summary}
          </Typography>
        </Box>
      </Box>
    </Row>
  );
}

function FindingRow({ e }: { e: Finding }) {
  return (
    <Row indent={1}>
      <Ts ts={e.ts} />
      <Box sx={{ display: "flex", alignItems: "flex-start", gap: 0.75, flex: 1 }}>
        <WarningAmberOutlinedIcon sx={{ fontSize: 11, color: concernColor(e.concern_type), mt: "2px", flexShrink: 0 }} />
        <Box sx={{ flex: 1 }}>
          <Stack direction="row" spacing={0.75} sx={{ alignItems: "center", mb: 0.3, flexWrap: "wrap" }}>
            <Chip label={e.concern_type.replace(/_/g, " ")} size="small" variant="outlined"
              sx={{ height: 16, fontSize: "0.56rem", color: concernColor(e.concern_type),
                    borderColor: concernColor(e.concern_type) + "55" }} />
            <Typography variant="caption"
              sx={{ fontFamily: "var(--font-google-sans-code)", color: "text.secondary", fontSize: "0.62rem" }}>
              {e.subject}
            </Typography>
          </Stack>
          <Typography variant="caption" sx={{ color: "text.disabled", fontSize: "0.63rem", lineHeight: 1.5 }}>
            {e.narrative}
          </Typography>
        </Box>
      </Box>
    </Row>
  );
}

function ActionPlannedRow({ e }: { e: ActionPlanned }) {
  return (
    <Row indent={1}>
      <Ts ts={e.ts} />
      <Box sx={{ display: "flex", alignItems: "center", gap: 0.75 }}>
        <AssignmentOutlinedIcon sx={{ fontSize: 11, color: "primary.light" }} />
        <Chip label={e.kind} size="small" variant="outlined"
          sx={{ height: 16, fontSize: "0.56rem", fontFamily: "var(--font-google-sans-code)",
                color: "primary.light", borderColor: "primary.dark" }} />
        <Typography variant="caption" sx={{ color: "text.secondary", fontSize: "0.63rem" }}>
          {e.title}
        </Typography>
      </Box>
    </Row>
  );
}

// ---------------------------------------------------------------------------
// Event dispatcher
// ---------------------------------------------------------------------------
function EventRow({ event, prevEvent }: { event: ActivityEvent; prevEvent?: ActivityEvent }) {
  switch (event.type) {
    case "run_start":      return prevEvent ? <><RunStartRow e={event} /></> : <RunStartRow e={event} />;
    case "run_end":        return <RunEndRow e={event} />;
    case "stage_start":    return <StageStartRow e={event} />;
    case "stage_end":      return <StageEndRow e={event} />;
    case "agent_text":     return <AgentTextRow e={event} />;
    case "tool_call":      return <ToolCallRow e={event} />;
    case "tool_response":  return <ToolResponseRow e={event} />;
    case "subagent_spawn": return <SubagentSpawnRow e={event} />;
    case "subagent_result":return <SubagentResultRow e={event} />;
    case "finding":        return <FindingRow e={event} />;
    case "action_planned": return <ActionPlannedRow e={event} />;
    default:               return null;
  }
}

// ---------------------------------------------------------------------------
// Stage progress bar (always-visible, extracted from event history)
// ---------------------------------------------------------------------------
function StageProgressBar({ events }: { events: ActivityEvent[] }) {
  const stages = useMemo(() => {
    const map: Record<string, { label: string; status: string; duration_ms?: number }> = {};
    for (const e of events) {
      if (e.type === "stage_start") map[e.stage_id] = { label: e.label, status: "running" };
      else if (e.type === "stage_end") map[e.stage_id] = { label: e.label, status: e.status, duration_ms: e.duration_ms };
    }
    return map;
  }, [events]);

  // Object.keys preserves insertion order — events arrive in execution order,
  // so this naturally renders stages in the order they ran without a hardcoded list.
  const seenIds = Object.keys(stages);
  if (seenIds.length === 0) return null;

  return (
    <Box sx={{ px: 1.5, py: 0.75, borderBottom: "1px solid rgba(255,255,255,0.06)",
               display: "flex", gap: 0.5, flexWrap: "wrap", flexShrink: 0,
               bgcolor: "rgba(255,255,255,0.01)" }}>
      {seenIds.map(id => {
        const s = stages[id];
        const color = s.status === "running" ? "primary" : s.status === "success" ? "success"
          : s.status === "failed" ? "error" : "default";
        const label = s.duration_ms != null
          ? `${s.label} ${fmtDuration(s.duration_ms)}`
          : s.label;
        return (
          <Tooltip key={id} title={s.status === "running" ? "running…" : s.status} arrow>
            <Chip
              label={label}
              size="small"
              color={color}
              variant={s.status === "running" ? "filled" : "outlined"}
              sx={{ height: 16, fontSize: "0.56rem", cursor: "default",
                    "& .MuiChip-label": { px: 0.75 } }}
            />
          </Tooltip>
        );
      })}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function ActivityFeed({ height = 640 }: { height?: number | string }) {
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const containerRef = useRef<HTMLDivElement>(null);
  const seenRef = useRef<Set<string>>(new Set());
  const didInitialScrollRef = useRef(false);
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  // Scroll to bottom once after the initial history batch is populated.
  useEffect(() => {
    if (!didInitialScrollRef.current && events.length > 0 && containerRef.current) {
      didInitialScrollRef.current = true;
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [events]);

  useEffect(() => {
    const es = new EventSource(`${apiUrl}/pipeline/activity/stream`);
    // Do NOT clear events on reconnect - history replay will fill them back in.
    // Clearing here is what causes the "disappears after tab switch" bug.
    es.onmessage = (e) => {
      try {
        const event = JSON.parse(e.data) as ActivityEvent;
        // A new run_start is the right time to show a clean feed.
        if (event.type === "run_start") {
          seenRef.current.clear();
          setEvents([]);
          didInitialScrollRef.current = false;
        }
        // Deduplicate: history replay can overlap with events already in state.
        const key = `${event.type}:${event.ts}:${(event as Record<string, unknown>).stage_id ?? ""}:${(event as Record<string, unknown>).run_id ?? ""}`;
        if (!seenRef.current.has(key)) {
          seenRef.current.add(key);
          setEvents((prev) => [...prev.slice(-999), event]);
        }
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
    <Stack spacing={0} sx={{ height, border: "1px solid rgba(255,255,255,0.08)", borderRadius: 1.5, overflow: "hidden" }}>
      {/* Header */}
      <Box sx={{ px: 2, py: 0.75, borderBottom: "1px solid rgba(255,255,255,0.06)",
          display: "flex", alignItems: "center", gap: 1,
          bgcolor: "rgba(255,255,255,0.02)", flexShrink: 0 }}>
        <SmartToyOutlinedIcon sx={{ fontSize: 13, color: "text.disabled" }} />
        <Typography variant="caption" color="text.disabled"
          sx={{ fontFamily: "var(--font-google-sans-code)", flex: 1, fontSize: "0.65rem" }}>
          Agent Activity
        </Typography>
        <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.58rem" }}>
          {events.length} events
        </Typography>
        <Tooltip title="Scroll to latest" placement="left" arrow>
          <IconButton size="small" onClick={scrollToBottom} sx={{ p: 0.5, color: "primary.main" }}>
            <KeyboardArrowDownIcon sx={{ fontSize: 16 }} />
          </IconButton>
        </Tooltip>
      </Box>

      {/* Stage progress bar - always visible regardless of scroll */}
      <StageProgressBar events={events} />

      {/* Feed - no auto-scroll; user controls position */}
      <Box ref={containerRef}
        sx={{ flex: 1, overflowY: "auto", p: 1.25, ...scrollbarSx }}>
        {events.length === 0 ? (
          <Typography variant="caption" color="text.disabled"
            sx={{ fontFamily: "var(--font-google-sans-code)", fontSize: "0.65rem" }}>
            Waiting for pipeline run…
          </Typography>
        ) : (
          events.map((event, i) => (
            <EventRow key={i} event={event} prevEvent={events[i - 1]} />
          ))
        )}
      </Box>
    </Stack>
  );
}
