import type { Metadata } from "next";
import { Google_Sans, Google_Sans_Code } from "next/font/google";
import ThemeRegistry from "./ThemeRegistry";
import Sidebar from "./components/Sidebar";
import "./globals.css";

const googleSans = Google_Sans({
  variable: "--font-google-sans",
  subsets: ["latin"],
  weight: "variable",
});

const googleSansCode = Google_Sans_Code({
  variable: "--font-google-sans-code",
  subsets: ["latin"],
  weight: "variable",
});

export const metadata: Metadata = {
  title: "Mycelium — Continuity Engine",
  description: "AI-powered engineering continuity agent powered by Gemini and GitLab MCP",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className={`${googleSans.variable} ${googleSansCode.variable}`}>
      <body>
        <ThemeRegistry>
          <div style={{ display: "flex", minHeight: "100vh" }}>
            <Sidebar />
            <div style={{ flex: 1, marginLeft: 220, minHeight: "100vh", overflowX: "hidden" }}>
              {children}
            </div>
          </div>
        </ThemeRegistry>
      </body>
    </html>
  );
}
