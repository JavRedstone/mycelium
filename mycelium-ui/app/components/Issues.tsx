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
import Link from "@mui/material/Link";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Tooltip from "@mui/material/Tooltip";
import Typography from "@mui/material/Typography";

import AssignmentOutlinedIcon from "@mui/icons-material/AssignmentOutlined";
import OpenInNewIcon from "@mui/icons-material/OpenInNew";
import RadioButtonUncheckedIcon from "@mui/icons-material/RadioButtonUnchecked";
import RefreshIcon from "@mui/icons-material/Refresh";

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type BotIssue = {
  iid: number;
  title: string;
  created_at: string | null;
  updated_at: string | null;
  labels: string[];
  web_url: string | null;
  bot_authored: boolean;
  assignee: string | null;
  description_preview: string | null;
};

// ---------------------------------------------------------------------------
// Label colours — keyed on lowercased label slug
// ---------------------------------------------------------------------------

const LABEL_PALETTE: Record<string, { text: string; bg: string }> = {
  "continuity":             { text: "#34a853", bg: "rgba(52,168,83,0.15)"   },
  "continuity-risk":        { text: "#34a853", bg: "rgba(52,168,83,0.15)"   },
  "knowledge_transfer":     { text: "#4285f4", bg: "rgba(66,133,244,0.15)"  },
  "knowledge_concentration":{ text: "#4285f4", bg: "rgba(66,133,244,0.15)"  },
  "knowledge-gap":          { text: "#4285f4", bg: "rgba(66,133,244,0.15)"  },
  "single-point-of-failure":{ text: "#4285f4", bg: "rgba(66,133,244,0.15)"  },
  "bus_factor":             { text: "#ea4335", bg: "rgba(234,67,53,0.14)"   },
  "security":               { text: "#ea4335", bg: "rgba(234,67,53,0.14)"   },
  "ownership":              { text: "#fa7b17", bg: "rgba(250,123,23,0.14)"  },
  "undeclared_ownership":   { text: "#fa7b17", bg: "rgba(250,123,23,0.14)"  },
  "codeowners":             { text: "#fa7b17", bg: "rgba(250,123,23,0.14)"  },
  "maintenance":            { text: "#fa7b17", bg: "rgba(250,123,23,0.14)"  },
  "documentation":          { text: "#fbbc04", bg: "rgba(251,188,4,0.13)"   },
  "upstream_dominance":     { text: "#c58af9", bg: "rgba(171,71,188,0.15)"  },
  "upstream-dominance":     { text: "#c58af9", bg: "rgba(171,71,188,0.15)"  },
  "upstream_drift":         { text: "#c58af9", bg: "rgba(171,71,188,0.15)"  },
  "upstream-drift":         { text: "#c58af9", bg: "rgba(171,71,188,0.15)"  },
  "dependency-update":      { text: "#c58af9", bg: "rgba(171,71,188,0.15)"  },
  "onboarding":             { text: "#34a853", bg: "rgba(52,168,83,0.15)"   },
  "gap":                    { text: "#9aa0a6", bg: "rgba(154,160,166,0.12)" },
};

const DEFAULT_PALETTE = { text: "#9aa0a6", bg: "rgba(154,160,166,0.10)" };

function labelPalette(label: string) {
  const key = label.toLowerCase().replace(/ /g, "_");
  return LABEL_PALETTE[key] ?? LABEL_PALETTE[label.toLowerCase()] ?? DEFAULT_PALETTE;
}

// ---------------------------------------------------------------------------
// Relative time helper
// ---------------------------------------------------------------------------

function relativeTime(iso: string | null): string {
  if (!iso) return "";
  const diffMs = Date.now() - new Date(iso).getTime();
  const mins   = Math.floor(diffMs / 60_000);
  const hours  = Math.floor(diffMs / 3_600_000);
  const days   = Math.floor(diffMs / 86_400_000);
  if (mins  < 2)  return "just now";
  if (mins  < 60) return `${mins}m ago`;
  if (hours < 24) return `${hours}h ago`;
  if (days  < 30) return `${days}d ago`;
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

// ---------------------------------------------------------------------------
// Single issue row — GitLab list style
// ---------------------------------------------------------------------------

function IssueRow({ issue, last }: { issue: BotIssue; last: boolean }) {
  const visibleLabels = issue.labels.filter((l) => l.toLowerCase() !== "mycelium");

  return (
    <Box>
      <Stack
        direction="row"
        sx={{ px: 2.5, py: 1.75, gap: 2, alignItems: "flex-start", "&:hover": { bgcolor: "rgba(255,255,255,0.025)" }, transition: "background 0.1s" }}
      >
        {/* Open-state indicator */}
        <Box sx={{ pt: 0.2, flexShrink: 0 }}>
          <RadioButtonUncheckedIcon sx={{ fontSize: 16, color: "#34a853" }} />
        </Box>

        {/* Main content */}
        <Box sx={{ flex: 1, minWidth: 0 }}>
          {/* Title */}
          <Stack direction="row" sx={{ alignItems: "center", gap: 1, flexWrap: "wrap" }}>
            {issue.web_url ? (
              <Link
                href={issue.web_url}
                target="_blank"
                rel="noopener noreferrer"
                underline="hover"
                sx={{ color: "text.primary", fontWeight: 600, fontSize: "0.9rem", lineHeight: 1.4 }}
              >
                {issue.title}
              </Link>
            ) : (
              <Typography sx={{ fontWeight: 600, fontSize: "0.9rem", lineHeight: 1.4, color: "text.primary" }}>
                {issue.title}
              </Typography>
            )}
          </Stack>

          {/* Labels */}
          {visibleLabels.length > 0 && (
            <Stack direction="row" sx={{ flexWrap: "wrap", gap: 0.5, mt: 0.75 }}>
              {visibleLabels.map((lbl) => {
                const p = labelPalette(lbl);
                return (
                  <Chip
                    key={lbl}
                    label={lbl}
                    size="small"
                    sx={{
                      height: 20,
                      fontSize: "0.62rem",
                      fontWeight: 500,
                      color: p.text,
                      bgcolor: p.bg,
                      border: "none",
                      borderRadius: "4px",
                      "& .MuiChip-label": { px: 1 },
                    }}
                  />
                );
              })}
            </Stack>
          )}

          {/* Description preview */}
          {issue.description_preview && (
            <Typography
              variant="caption"
              color="text.disabled"
              sx={{ display: "block", mt: 0.75, lineHeight: 1.5, fontSize: "0.72rem", whiteSpace: "pre-line" }}
            >
              {issue.description_preview.replace(/#{1,6} /g, "").replace(/\*\*/g, "").slice(0, 160)}
              {(issue.description_preview.length > 160) && "…"}
            </Typography>
          )}

          {/* Meta row */}
          <Stack direction="row" sx={{ gap: 1.5, mt: 0.75, alignItems: "center", flexWrap: "wrap" }}>
            <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.68rem" }}>
              #{issue.iid} opened {relativeTime(issue.created_at)} by Mycelium
            </Typography>
            {issue.assignee && (
              <Typography variant="caption" color="text.disabled" sx={{ fontSize: "0.68rem" }}>
                · assigned to {issue.assignee}
              </Typography>
            )}
          </Stack>
        </Box>

        {/* Right: GitLab link */}
        {issue.web_url && (
          <Tooltip title="Open in GitLab" placement="left">
            <Link
              href={issue.web_url}
              target="_blank"
              rel="noopener noreferrer"
              sx={{ color: "text.disabled", display: "flex", alignItems: "center", flexShrink: 0, mt: 0.2, "&:hover": { color: "primary.light" } }}
            >
              <OpenInNewIcon sx={{ fontSize: 14 }} />
            </Link>
          </Tooltip>
        )}
      </Stack>

      {!last && <Divider sx={{ borderColor: "rgba(255,255,255,0.05)", mx: 2.5 }} />}
    </Box>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export default function Issues() {
  const [issues, setIssues]   = useState<BotIssue[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);

  const fetchIssues = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API}/gitlab/bot-issues`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const raw: BotIssue[] = data.issues ?? [];
      setIssues([...raw].sort((a, b) => b.iid - a.iid));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fetch failed");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { fetchIssues(); }, [fetchIssues]);

  return (
    <Stack spacing={2}>
      {/* Toolbar */}
      <Stack direction="row" sx={{ alignItems: "center", justifyContent: "space-between" }}>
        <Stack direction="row" spacing={1} sx={{ alignItems: "center" }}>
          {!loading && issues.length > 0 && (
            <Typography variant="caption" color="text.disabled">
              {issues.length} open issue{issues.length !== 1 ? "s" : ""}
            </Typography>
          )}
          {loading && <CircularProgress size={14} />}
        </Stack>
        <Button
          size="small"
          variant="outlined"
          onClick={fetchIssues}
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

      {!loading && issues.length === 0 && !error && (
        <Paper
          elevation={0}
          sx={{ p: 5, textAlign: "center", border: "1px solid rgba(255,255,255,0.06)", borderRadius: 2 }}
        >
          <AssignmentOutlinedIcon sx={{ fontSize: 36, color: "text.disabled", mb: 1.5 }} />
          <Typography variant="body2" color="text.disabled">
            No open Mycelium issues.
          </Typography>
          <Typography variant="caption" color="text.disabled">
            Run the pipeline to create continuity interventions.
          </Typography>
        </Paper>
      )}

      {issues.length > 0 && (
        <Paper
          elevation={0}
          sx={{ border: "1px solid rgba(255,255,255,0.08)", borderRadius: 2, overflow: "hidden" }}
        >
          {/* List header */}
          <Stack
            direction="row"
            sx={{
              px: 2.5,
              py: 1.25,
              bgcolor: "rgba(255,255,255,0.03)",
              borderBottom: "1px solid rgba(255,255,255,0.06)",
              alignItems: "center",
              gap: 1,
            }}
          >
            <RadioButtonUncheckedIcon sx={{ fontSize: 14, color: "text.disabled" }} />
            <Typography variant="caption" sx={{ fontWeight: 600, color: "text.secondary" }}>
              {issues.length} Open
            </Typography>
          </Stack>

          {/* Issue rows */}
          {issues.map((issue, i) => (
            <IssueRow key={issue.iid} issue={issue} last={i === issues.length - 1} />
          ))}
        </Paper>
      )}
    </Stack>
  );
}
