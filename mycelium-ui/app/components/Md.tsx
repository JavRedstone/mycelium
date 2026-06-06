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

﻿"use client";

import ReactMarkdown from "react-markdown";
import Box from "@mui/material/Box";

/**
 * Renders a markdown string using the dark-theme palette.
 * Safe to drop inside any MUI component that renders as a block element (Box, div, etc.).
 * The parent must NOT be a <p> - use Typography component="div" or plain Box.
 */
export default function Md({ children, compact = false }: { children: string; compact?: boolean }) {
  if (!children) return null;
  const textSize = compact ? "0.75rem" : "0.875rem";
  const codeSize = compact ? "0.68rem" : "0.8em";
  return (
    <Box
      sx={{
        "& p": { m: 0, mb: 0.75, lineHeight: 1.65, fontSize: textSize, color: "text.secondary" },
        "& p:last-child": { mb: 0 },
        "& ul, & ol": { pl: 2.5, my: 0.25, color: "text.secondary" },
        "& li": { mb: 0.25, fontSize: textSize, lineHeight: 1.6 },
        "& strong": { fontWeight: 600, color: "text.primary" },
        "& em": { fontStyle: "italic", color: "text.secondary" },
        "& code": {
          fontFamily: "var(--font-google-sans-code)",
          fontSize: codeSize,
          bgcolor: "rgba(255,255,255,0.07)",
          px: 0.5,
          py: 0.125,
          borderRadius: 0.5,
        },
        "& pre": {
          bgcolor: "rgba(255,255,255,0.04)",
          p: compact ? 1 : 1.5,
          borderRadius: 1,
          overflow: "auto",
          maxHeight: compact ? 200 : "none",
          "& code": { bgcolor: "transparent", p: 0, fontSize: codeSize },
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
