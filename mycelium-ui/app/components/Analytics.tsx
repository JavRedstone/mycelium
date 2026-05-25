"use client";

import { useCallback, useEffect, useState } from "react";
import Box from "@mui/material/Box";
import Card from "@mui/material/Card";
import CardContent from "@mui/material/CardContent";
import Chip from "@mui/material/Chip";
import CircularProgress from "@mui/material/CircularProgress";
import Grid from "@mui/material/Grid";
import Paper from "@mui/material/Paper";
import Stack from "@mui/material/Stack";
import Typography from "@mui/material/Typography";
import IconButton from "@mui/material/IconButton";
import RefreshIcon from "@mui/icons-material/Refresh";
import ErrorOutlinedIcon from "@mui/icons-material/ErrorOutlined";
import WarningAmberOutlinedIcon from "@mui/icons-material/WarningAmberOutlined";
import ShieldOutlinedIcon from "@mui/icons-material/ShieldOutlined";
import GroupOutlinedIcon from "@mui/icons-material/GroupOutlined";
import HubOutlinedIcon from "@mui/icons-material/HubOutlined";
import { filterModules } from "../lib/graphFilters";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

// ---------------------------------------------------------------------------
// Types - measurements only, no scores
// ---------------------------------------------------------------------------
type Contributor = {
  developer_username: string;
  developer_identity: string;
  commit_count: number;
  expertise_score: number;
  external: boolean;
};

type Module = {
  path: string;
  owners: string[];
  bus_factor: number;
  contributors: Contributor[];
};

type Developer = {
  username: string;
  name: string;
  active: boolean;
  external: boolean;
};

type Finding = {
  subject: string;
  concern_type: string;
  narrative: string;
};

type GraphData = {
  developers: Developer[];
  upstream_authors: Developer[];
  modules: Module[];
  concentrated_modules?: Module[];
  recent_findings?: Finding[];
};

// ---------------------------------------------------------------------------
// Palettes
// ---------------------------------------------------------------------------
// Bus factor: red → green encodes risk level (1 committer = danger, 5+ = safe).
const BUS_COLORS = ["#ea4335", "#fa7b17", "#fbbc04", "#34a853", "#1a73e8"];

// Concern-type bars: single accent - the Y-axis label already identifies each bar,
// so multiple colours add noise rather than information.
const CONCERN_BAR_COLOR = "#1a73e8";

// ---------------------------------------------------------------------------
// Chart tooltip + stat card
// ---------------------------------------------------------------------------
function ChartTooltip({ active, payload, label }: {
  active?: boolean;
  payload?: { name: string; value: number; fill: string }[];
  label?: string;
}) {
  if (!active || !payload?.length) return null;
  return (
    <Paper sx={{ px: 1.5, py: 1, bgcolor: "#21262d", border: "1px solid rgba(255,255,255,0.1)", boxShadow: "0 4px 16px rgba(0,0,0,0.4)" }}>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>{label}</Typography>
      {payload.map((p) => (
        <Typography key={p.name} variant="caption" sx={{ display: "block", color: p.fill, fontWeight: 600 }}>
          {p.value}
        </Typography>
      ))}
    </Paper>
  );
}

// warn=true → value shown in orange (one consistent alert colour); icon is always neutral.
function StatCard({ label, value, sub, warn, icon }: {
  label: string; value: number | string; sub?: string; warn?: boolean; icon: React.ReactNode;
}) {
  return (
    <Card>
      <CardContent sx={{ p: 2.5, "&:last-child": { pb: 2.5 } }}>
        <Stack direction="row" sx={{ alignItems: "flex-start", justifyContent: "space-between" }}>
          <Box>
            <Typography variant="caption" color="text.secondary" sx={{ textTransform: "uppercase", letterSpacing: "0.06em", fontSize: "0.68rem" }}>
              {label}
            </Typography>
            <Typography variant="h4" sx={{ fontWeight: 700, mt: 0.5, color: warn ? "#fa7b17" : "text.primary" }}>
              {value}
            </Typography>
            {sub && (
              <Typography variant="caption" color="text.secondary" sx={{ mt: 0.25, display: "block" }}>
                {sub}
              </Typography>
            )}
          </Box>
          <Box sx={{ color: "text.secondary", mt: 0.25 }}>{icon}</Box>
        </Stack>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------
export default function Analytics() {
  const [data, setData] = useState<GraphData | null>(null);
  const [findings, setFindings] = useState<Finding[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  const apiUrl = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [graphRes, findingsRes] = await Promise.all([
        fetch(`${apiUrl}/graph`),
        fetch(`${apiUrl}/findings?limit=200`),
      ]);
      if (!graphRes.ok) throw new Error(`HTTP ${graphRes.status}`);
      const graphJson = (await graphRes.json()) as GraphData;
      setData(graphJson);
      if (findingsRes.ok) {
        setFindings((await findingsRes.json()) as Finding[]);
      } else {
        setFindings(graphJson.recent_findings ?? []);
      }
      setLastUpdated(new Date());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Fetch failed");
    } finally {
      setLoading(false);
    }
  }, [apiUrl]);

  useEffect(() => { fetchData(); }, [fetchData]);

  // ---- Derived measurements (no scoring, no severity) ----
  const modules = filterModules(data?.modules ?? []);
  const concentrated = modules.filter((m) => m.bus_factor <= 1);
  const unowned = modules.filter((m) => !m.owners || m.owners.length === 0);

  // Bus factor distribution (a measurement, kept)
  const bfMap = new Map<number, number>();
  modules.forEach((m) => {
    const bf = Math.min(m.bus_factor, 5);
    bfMap.set(bf, (bfMap.get(bf) ?? 0) + 1);
  });
  const bfDist = Array.from(bfMap.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([bf, count]) => ({ name: bf >= 5 ? "5+" : String(bf), count }));

  // Findings by concern type (replaces risk severity distribution - descriptive, not magnitude)
  const concernMap = new Map<string, number>();
  findings.forEach((f) => {
    const k = f.concern_type ?? "unspecified";
    concernMap.set(k, (concernMap.get(k) ?? 0) + 1);
  });
  const concernDist = Array.from(concernMap.entries())
    .sort((a, b) => b[1] - a[1])
    .map(([type, count]) => ({ name: type.replace(/_/g, " "), count, type }));
  // Give every bar enough vertical room so Recharts never drops a label
  const concernChartHeight = Math.max(200, concernDist.length * 40);

  // Developer load (still valid - a measurement, not a score)
  const devCommits = new Map<string, number>();
  modules.forEach((m) =>
    m.contributors.forEach((c) => {
      devCommits.set(c.developer_username, (devCommits.get(c.developer_username) ?? 0) + c.commit_count);
    }),
  );
  const topDevs = Array.from(devCommits.entries())
    .sort((a, b) => b[1] - a[1])
    .slice(0, 10)
    .map(([dev, commits]) => ({ name: dev, commits }));
  const devChartHeight = Math.max(200, topDevs.length * 40);

  if (loading && !data) {
    return (
      <Box sx={{ display: "flex", alignItems: "center", gap: 1.5, color: "text.secondary", py: 4 }}>
        <CircularProgress size={18} />
        <Typography variant="body2">Loading analytics…</Typography>
      </Box>
    );
  }

  if (error && !data) {
    return (
      <Box sx={{ display: "flex", alignItems: "center", gap: 1, color: "error.main", py: 4 }}>
        <ErrorOutlinedIcon fontSize="small" />
        <Typography variant="body2">{error}</Typography>
      </Box>
    );
  }

  return (
    <Stack spacing={3}>
      {/* Toolbar */}
      <Stack direction="row" sx={{ alignItems: "center", justifyContent: "space-between" }}>
        <Stack direction="row" sx={{ alignItems: "center" }} spacing={1}>
          {lastUpdated && (
            <Typography variant="caption" color="text.secondary">
              Updated {lastUpdated.toLocaleTimeString()}
            </Typography>
          )}
          {loading && <CircularProgress size={14} />}
        </Stack>
        <IconButton size="small" onClick={fetchData} disabled={loading} sx={{ color: "text.secondary" }}>
          <RefreshIcon fontSize="small" />
        </IconButton>
      </Stack>

      {/* Observational stats */}
      <Grid container spacing={2}>
        <Grid size={{ xs: 6, sm: 3 }}>
          <StatCard label="Total Modules" value={modules.length} icon={<ShieldOutlinedIcon />} />
        </Grid>
        <Grid size={{ xs: 6, sm: 3 }}>
          <StatCard
            label="Bus Factor ≤ 1"
            value={concentrated.length}
            sub="Single internal committer"
            warn={concentrated.length > 0}
            icon={<WarningAmberOutlinedIcon />}
          />
        </Grid>
        <Grid size={{ xs: 6, sm: 3 }}>
          <StatCard
            label="Unowned Modules"
            value={unowned.length}
            sub="No CODEOWNERS entry"
            warn={unowned.length > 0}
            icon={<HubOutlinedIcon />}
          />
        </Grid>
        <Grid size={{ xs: 6, sm: 3 }}>
          <StatCard
            label="Upstream Authors"
            value={data?.upstream_authors?.length ?? 0}
            sub="External knowledge holders"
            warn={(data?.upstream_authors?.length ?? 0) > 0}
            icon={<GroupOutlinedIcon />}
          />
        </Grid>
      </Grid>

      {/* Findings by concern type */}
      <Paper sx={{ p: 2.5 }}>
        <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 0.5 }} color="text.primary">
          Findings by Concern Type
        </Typography>
        <Typography variant="caption" color="text.disabled" sx={{ display: "block", mb: 2 }}>
          Descriptive categories from the analyst&apos;s qualitative findings.
        </Typography>
        {concernDist.length === 0 ? (
          <Typography variant="body2" color="text.disabled">
            No findings yet. Run the pipeline to populate.
          </Typography>
        ) : (
          <ResponsiveContainer width="100%" height={concernChartHeight}>
            <BarChart data={concernDist} layout="vertical" barSize={20} margin={{ left: 0, right: 32, top: 4, bottom: 20 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" horizontal={false} />
              <XAxis
                type="number"
                tick={{ fill: "#9198a1", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                allowDecimals={false}
                label={{ value: "Count", position: "insideBottomRight", offset: -4, style: { fill: "#9198a1", fontSize: 11 } }}
              />
              <YAxis
                type="category"
                dataKey="name"
                width={210}
                tick={{ fill: "#9198a1", fontSize: 11 }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
              <Bar dataKey="count" fill={CONCERN_BAR_COLOR} radius={[0, 4, 4, 0]} />
            </BarChart>
          </ResponsiveContainer>
        )}
      </Paper>

      {/* Bus factor + developer load */}
      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 6 }}>
          <Paper sx={{ p: 2.5 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 2 }} color="text.primary">
              Bus Factor Distribution (measurement)
            </Typography>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={bfDist} barSize={36}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                <XAxis
                  dataKey="name"
                  tick={{ fill: "#9198a1", fontSize: 12 }}
                  axisLine={{ stroke: "rgba(255,255,255,0.1)" }}
                  tickLine={false}
                  label={{ value: "# Internal Committers", position: "insideBottom", offset: -2, style: { fill: "#9198a1", fontSize: 11 } }}
                />
                <YAxis tick={{ fill: "#9198a1", fontSize: 12 }} axisLine={false} tickLine={false} allowDecimals={false} />
                <Tooltip content={<ChartTooltip />} cursor={{ fill: "rgba(255,255,255,0.04)" }} />
                <Bar dataKey="count" radius={[4, 4, 0, 0]}>
                  {bfDist.map((entry, i) => (
                    <Cell key={entry.name} fill={BUS_COLORS[Math.min(i, BUS_COLORS.length - 1)]} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </Paper>
        </Grid>

        <Grid size={{ xs: 12, md: 6 }}>
          <Paper sx={{ p: 2.5 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 600, mb: 2 }} color="text.primary">
              Developer Knowledge Load (commits)
            </Typography>
            <ResponsiveContainer width="100%" height={devChartHeight}>
              <BarChart data={topDevs} layout="vertical" barSize={20} margin={{ left: 0, right: 32, top: 4, bottom: 20 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" horizontal={false} />
                <XAxis
                  type="number"
                  tick={{ fill: "#9198a1", fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                  allowDecimals={false}
                  label={{ value: "Commits", position: "insideBottomRight", offset: -4, style: { fill: "#9198a1", fontSize: 11 } }}
                />
                <YAxis
                  type="category"
                  dataKey="name"
                  width={160}
                  tick={{ fill: "#9198a1", fontSize: 11 }}
                  axisLine={false}
                  tickLine={false}
                />
                <Tooltip
                  cursor={{ fill: "rgba(255,255,255,0.04)" }}
                  content={({ active, payload, label }) =>
                    active && payload?.length ? (
                      <Paper sx={{ px: 1.5, py: 1, bgcolor: "#21262d", border: "1px solid rgba(255,255,255,0.1)" }}>
                        <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>{label}</Typography>
                        <Typography variant="caption" sx={{ color: "#1a73e8", fontWeight: 600 }}>{payload[0].value} commits</Typography>
                      </Paper>
                    ) : null
                  }
                />
                <Bar dataKey="commits" fill="#1a73e8" radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Paper>
        </Grid>
      </Grid>

      <Chip
        label={`${modules.length} modules · ${findings.length} findings · ${concentrated.length} bus-factor-1`}
        size="small"
        variant="outlined"
        sx={{ height: 20, fontSize: "0.68rem", color: "text.secondary", borderColor: "divider", alignSelf: "flex-start" }}
      />
    </Stack>
  );
}
