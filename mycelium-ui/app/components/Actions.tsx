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

"use client";

import { useCallback, useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Button from "@mui/material/Button";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Divider from "@mui/material/Divider";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";

import BoltOutlinedIcon from "@mui/icons-material/BoltOutlined";
import CheckCircleOutlinedIcon from "@mui/icons-material/CheckCircleOutlined";
import ErrorOutlinedIcon from "@mui/icons-material/ErrorOutlined";
import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import RefreshIcon from "@mui/icons-material/Refresh";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------
type ActionRecord = {
  id: string;
  run_id: string;
  executed_at: string;
  tool: string;
  detail: string;
  success: boolean;
  run_summary: string | null;
};

type RunGroup = {
  run_id: string;
  executed_at: string;
  actions: ActionRecord[];
  summary: string | null;
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
const TOOL_LABELS: Record<string, string> = {
  create_issue: "Issue",
  createIssue: "Issue",
  create_merge_request: "MR",
  createMergeRequest: "MR",
  add_comment: "Comment",
  addComment: "Comment",
  comment_on_issue: "Comment",
  comment_on_mr: "MR Comment",
  assign_issue: "Assignment",
  assignIssue: "Assignment",
  assess: "Assessment",
};

function toolLabel(tool: string): string {
  return TOOL_LABELS[tool] ?? tool.replace(/_/g, " ");
}

function toolColor(tool: string, success: boolean): string {
  if (!success) return "#ea4335";
  if (tool === "assess") return "#4285f4";
  if (tool.includes("issue") || tool.includes("Issue")) return "#34a853";
  if (tool.includes("mr") || tool.includes("MR") || tool.includes("merge")) return "#fbbc04";
  if (tool.includes("comment") || tool.includes("Comment")) return "#4285f4";
  if (tool.includes("assign") || tool.includes("Assign")) return "#fa7b17";
  return "#8ab4f8";
}

function formatRunId(runId: string): string {
  return runId.slice(0, 8);
}

function formatTs(iso: string): string {
  // Force UTC parsing — backend stores in UTC but may omit the Z suffix,
  // which causes browsers to misinterpret the string as local time.
  const utc = iso.endsWith("Z") || iso.includes("+") ? iso : iso + "Z";
  const ts = Math.floor(new Date(utc).getTime() / 1000);
  if (isNaN(ts)) return iso;
  const diff = Math.floor(Date.now() / 1000 - ts);
  if (diff < 5)   return "just now";
  if (diff < 60)  return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

// ---------------------------------------------------------------------------
// Group flat action records by run_id, preserving insertion order (desc by time)
// ---------------------------------------------------------------------------
function groupByRun(records: ActionRecord[]): RunGroup[] {
  const map = new Map<string, RunGroup>();
  for (const r of records) {
    if (!map.has(r.run_id)) {
      map.set(r.run_id, {
        run_id: r.run_id,
        executed_at: r.executed_at,
        actions: [],
        summary: r.run_summary ?? null,
      });
    }
    map.get(r.run_id)!.actions.push(r);
  }
  return [...map.values()];
}

// ---------------------------------------------------------------------------
// Single run card
// ---------------------------------------------------------------------------
function RunCard({ group }: { group: RunGroup }) {
  const actionCount = group.actions.filter((a) => a.tool !== "assess").length;
  const isAssessOnly = actionCount === 0;

  return (
    <Paper
      elevation={0}
      sx={{
        overflow: "hidden",
        border: "1px solid",
        borderColor: isAssessOnly ? "rgba(255,255,255,0.06)" : "rgba(52,168,83,0.2)",
        borderRadius: 2,
      }}
    >
      {/* Run header */}
      <Stack
        direction="row"
        sx={{
          alignItems: "center",
          px: 2.5,
          py: 1.5,
          bgcolor: isAssessOnly ? "rgba(255,255,255,0.02)" : "rgba(52,168,83,0.04)",
        }}
        spacing={1.5}
      >
        <BoltOutlinedIcon sx={{ fontSize: 16, color: isAssessOnly ? "text.disabled" : "success.light", flexShrink: 0 }} />
        <Typography variant="caption" sx={{ fontFamily: "var(--font-google-sans-code)", color: "text.secondary" }}>
          Run {formatRunId(group.run_id)}
        </Typography>
        <Typography variant="caption" color="text.disabled">
          {formatTs(group.executed_at)}
        </Typography>
        <Box sx={{ flex: 1 }} />
        <Chip
          label={isAssessOnly ? "No actions taken" : `${actionCount} action${actionCount !== 1 ? "s" : ""}`}
          size="small"
          variant="outlined"
          sx={{
            height: 20,
            fontSize: "0.65rem",
            color: isAssessOnly ? "text.disabled" : "success.light",
            borderColor: isAssessOnly ? "rgba(255,255,255,0.1)" : "rgba(52,168,83,0.4)",
          }}
        />
      </Stack>

      {/* Agent summary */}
      {group.summary && (
        <>
          <Divider sx={{ borderColor: "rgba(255,255,255,0.06)" }} />
          <Stack direction="row" spacing={1} sx={{ px: 2.5, py: 1.25, alignItems: "flex-start" }}>
            <InfoOutlinedIcon sx={{ fontSize: 13, color: "text.disabled", flexShrink: 0, mt: 0.25 }} />
            <Typography variant="caption" color="text.secondary" sx={{ lineHeight: 1.6 }}>
              {group.summary}
            </Typography>
          </Stack>
        </>
      )}

      {/* Action rows */}
      {group.actions.length > 0 && (
        <>
          <Divider sx={{ borderColor: "rgba(255,255,255,0.06)" }} />
          <Box sx={{ px: 2.5, py: 1 }}>
            <Stack spacing={0.5} sx={{ py: 0.5 }}>
              {group.actions.map((action) => {
                const color = toolColor(action.tool, action.success);
                return (
                  <Stack key={action.id} direction="row" spacing={1.5} sx={{ alignItems: "center", py: 0.25 }}>
                    {action.success
                      ? <CheckCircleOutlinedIcon sx={{ fontSize: 13, color: "success.light", flexShrink: 0 }} />
                      : <ErrorOutlinedIcon sx={{ fontSize: 13, color: "error.light", flexShrink: 0 }} />
                    }
                    <Chip
                      label={toolLabel(action.tool)}
                      size="small"
                      variant="outlined"
                      sx={{
                        height: 18,
                        fontSize: "0.6rem",
                        minWidth: 72,
                        color,
                        borderColor: color + "55",
                        bgcolor: color + "10",
                        flexShrink: 0,
                      }}
                    />
                    <Typography
                      variant="caption"
                      sx={{
                        fontFamily: "var(--font-google-sans-code)",
                        color: action.tool === "assess" ? "text.disabled" : "text.secondary",
                        flex: 1,
                        overflow: "hidden",
                        textOverflow: "ellipsis",
                        whiteSpace: "nowrap",
                      }}
                    >
                      {action.detail}
                    </Typography>
                  </Stack>
                );
              })}
            </Stack>
          </Box>
        </>
      )}
    </Paper>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function Actions() {
  const [records, setRecords] = useState<ActionRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  const fetchActions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiUrl}/actions`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setRecords(await res.json());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fetch failed");
    } finally {
      setLoading(false);
    }
  }, [apiUrl]);

  useEffect(() => { fetchActions(); }, [fetchActions]);

  const groups = groupByRun(records);

  return (
    <Stack spacing={2.5}>
      {/* Toolbar */}
      <Stack direction="row" sx={{ alignItems: "center", justifyContent: "space-between" }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
          {records.length > 0 && (
            <Typography variant="caption" color="text.disabled">
              {groups.length} run{groups.length !== 1 ? "s" : ""} · {records.filter((r) => r.tool !== "assess").length} actions
            </Typography>
          )}
          {loading && <CircularProgress size={14} />}
        </Stack>
        <Button
          size="small"
          variant="outlined"
          onClick={fetchActions}
          disabled={loading}
          startIcon={<RefreshIcon />}
          sx={{ height: 30 }}
        >
          {loading ? "Loading…" : "Refresh"}
        </Button>
      </Stack>

      {error && (
        <Typography variant="body2" color="error.main">{error}</Typography>
      )}

      {!loading && groups.length === 0 && !error && (
        <Paper elevation={0} sx={{ p: 4, textAlign: "center" }}>
          <BoltOutlinedIcon sx={{ fontSize: 32, color: "text.disabled", mb: 1 }} />
          <Typography variant="body2" color="text.disabled">
            No actions yet. Run the pipeline to let the agent take corrective action.
          </Typography>
        </Paper>
      )}

      {groups.map((group) => (
        <RunCard key={group.run_id} group={group} />
      ))}
    </Stack>
  );
}
