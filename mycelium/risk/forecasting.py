# Copyright 2026 Javier Huang
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Observational measurements only - no scoring, no aggregation.

Per PROJECT_IDEA, this system does not compute scalar risk scores. The functions
here produce raw counts and structural facts that the analyst agent reasons over
(alongside investigator findings) to produce qualitative Findings.

The file name is kept as forecasting.py for import stability, but the content
is now strictly measurement.
"""


def compute_bus_factor(contributions: list[dict]) -> int:
    """Number of contributors whose combined expertise covers >= 80% of a module.

    This is a count, not a risk score. The analyst interprets the count in
    context (with investigator findings, documentation state, etc.) when it
    decides whether a low bus factor matters for a given module.
    """
    if not contributions:
        return 0
    scores = sorted([c["expertise_score"] for c in contributions], reverse=True)
    total = sum(scores)
    if total == 0:
        return 0
    cumulative = 0.0
    for i, s in enumerate(scores):
        cumulative += s
        if cumulative / total >= 0.8:
            return i + 1
    return len(scores)
