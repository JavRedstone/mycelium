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
  title: "Mycelium: Continuity Engine",
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
