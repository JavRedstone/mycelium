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
