/**
 * Shared MUI sx style constants.
 *
 * Import these where you need consistent scrollbar / layout styling
 * rather than duplicating the same object across components.
 */

/**
 * Thin dark scrollbar - use on any `overflowY` / `overflowX` / `overflow` element.
 * Works for both vertical (width) and horizontal (height) scrollbars simultaneously.
 */
export const scrollbarSx = {
  "&::-webkit-scrollbar": { width: 4, height: 4 },
  "&::-webkit-scrollbar-track": { bgcolor: "transparent" },
  "&::-webkit-scrollbar-thumb": { bgcolor: "rgba(255,255,255,0.1)", borderRadius: 2 },
} as const;
