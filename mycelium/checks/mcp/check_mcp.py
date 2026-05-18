import subprocess
import sys
from pathlib import Path

checks_dir = Path(__file__).parent

for check in ["check_mcp_gitlab.py", "check_mcp_mongo.py"]:
    subprocess.run([sys.executable, str(checks_dir / check)])
