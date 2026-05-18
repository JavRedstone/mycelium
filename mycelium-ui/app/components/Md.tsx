"use client";

import ReactMarkdown from "react-markdown";
import Box from "@mui/material/Box";

/**
 * Renders a markdown string using the dark-theme palette.
 * Safe to drop inside any MUI component that renders as a block element (Box, div, etc.).
 * The parent must NOT be a <p> — use Typography component="div" or plain Box.
 */
export default function Md({ children }: { children: string }) {
  if (!children) return null;
  return (
    <Box
      sx={{
        "& p": { m: 0, mb: 0.75, lineHeight: 1.65, fontSize: "0.875rem", color: "text.secondary" },
        "& p:last-child": { mb: 0 },
        "& ul, & ol": { pl: 2.5, my: 0.25, color: "text.secondary" },
        "& li": { mb: 0.25, fontSize: "0.875rem", lineHeight: 1.6 },
        "& strong": { fontWeight: 600, color: "text.primary" },
        "& em": { fontStyle: "italic", color: "text.secondary" },
        "& code": {
          fontFamily: "var(--font-google-sans-code)",
          fontSize: "0.8em",
          bgcolor: "rgba(255,255,255,0.07)",
          px: 0.5,
          py: 0.125,
          borderRadius: 0.5,
        },
        "& pre": {
          bgcolor: "rgba(255,255,255,0.04)",
          p: 1.5,
          borderRadius: 1,
          overflow: "auto",
          "& code": { bgcolor: "transparent", p: 0 },
        },
        "& blockquote": {
          borderLeft: "3px solid rgba(255,255,255,0.2)",
          pl: 1.5,
          ml: 0,
          color: "text.disabled",
          fontStyle: "italic",
        },
      }}
    >
      <ReactMarkdown>{children}</ReactMarkdown>
    </Box>
  );
}
