import subprocess
import sys
from pathlib import Path

checks = ["check_mongo.py", "check_gitlab.py", "check_gemini.py"]
checks_dir = Path(__file__).parent

for check in checks:
    subprocess.run([sys.executable, str(checks_dir / check)])
