"use client";
import { createTheme } from "@mui/material/styles";

const theme = createTheme({
  palette: {
    mode: "dark",
    primary: { main: "#1a73e8", light: "#4da0ff", dark: "#0d47a1" },
    secondary: { main: "#34a853" },
    error: { main: "#ea4335" },
    warning: { main: "#fbbc04" },
    success: { main: "#34a853" },
    background: {
      default: "#0d1117",
      paper: "#161b22",
    },
    divider: "rgba(255,255,255,0.08)",
    text: {
      primary: "#e6edf3",
      secondary: "#9198a1",   // was #8b949e - slightly brighter for labels
      disabled: "#768390",    // was #484f58 - that was <2:1 contrast, unreadable
    },
  },
  typography: {
    fontFamily: "var(--font-google-sans), 'Google Sans', Arial, sans-serif",
    h1: { fontWeight: 500 },
    h2: { fontWeight: 500 },
    h3: { fontWeight: 500 },
    h4: { fontWeight: 500 },
    h5: { fontWeight: 500 },
    h6: { fontWeight: 500 },
    button: { textTransform: "none", fontWeight: 500 },
    caption: { fontSize: "0.75rem" },
    overline: { letterSpacing: "0.08em" },
  },
  shape: { borderRadius: 8 },
  components: {
    MuiPaper: {
      styleOverrides: {
        root: {
          backgroundImage: "none",
          border: "1px solid rgba(255,255,255,0.08)",
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          backgroundImage: "none",
          border: "1px solid rgba(255,255,255,0.08)",
        },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { fontWeight: 500 },
      },
    },
    MuiButton: {
      styleOverrides: {
        root: { borderRadius: 6 },
      },
    },
    MuiLinearProgress: {
      styleOverrides: {
        root: { borderRadius: 4, height: 3 },
      },
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          backgroundColor: "#21262d",
          border: "1px solid rgba(255,255,255,0.1)",
          fontSize: "0.75rem",
        },
      },
    },
  },
});

export default theme;
