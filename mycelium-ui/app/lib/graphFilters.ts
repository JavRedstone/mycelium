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

﻿/**
 * Shared graph data filters - applied identically across every component.
 *
 * "repository" is a synthetic catch-all node the pipeline writes to track
 * whole-repo contributors (module_path = "repository", expertise_score = 0.0).
 * It is NOT a real directory and must never appear in any UI list.
 *
 * Namespace-path entries (e.g. "gitlab-org/maintainers/gitlab-pages") are GitLab
 * bot/service-account artefacts from upstream fork history.  Real directory names
 * and real usernames never contain "/".
 *
 * Bot usernames that survived the "/" → "_" sanitisation are identified by
 * known segments ("maintainers", "gitlab-org", "noreply").
 */

const BOT_USERNAME_SEGMENTS = ["maintainers", "gitlab-org", "gitlab_org", "noreply"] as const;

export function isBotUsername(username: string): boolean {
  if (username.includes("/")) return true;
  const lower = username.toLowerCase();
  return BOT_USERNAME_SEGMENTS.some((seg) => lower.includes(seg));
}

export function isRealModulePath(path: string): boolean {
  return path !== "repository" && !path.includes("/");
}

/** Filter a raw modules array from the /graph API to only real, displayable modules. */
export function filterModules<T extends { path: string; contributors?: Array<{ developer_username: string }> }>(
  modules: T[]
): T[] {
  return modules
    .filter((m) => isRealModulePath(m.path))
    .map((m) => ({
      ...m,
      contributors: (m.contributors ?? []).filter(
        (c) => !isBotUsername(c.developer_username)
      ),
    })) as T[];
}
