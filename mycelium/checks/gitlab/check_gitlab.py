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

from dotenv import load_dotenv
import os
import gitlab

load_dotenv()

gl = gitlab.Gitlab(
    url=os.getenv("GITLAB_URL", "https://gitlab.com"),
    private_token=os.environ["GITLAB_TOKEN"],
)

try:
    gl.auth()
    project_id = int(os.environ["GITLAB_PROJECT_ID"])
    project = gl.projects.get(project_id)
    print(f"[OK] GitLab - authenticated as {gl.user.username}")
    print(f"[OK] GitLab - project '{project.name}' accessible")
except Exception as e:
    print(f"[FAIL] GitLab - {e}")
