import subprocess
import sys
from pathlib import Path
import re

from rich import print
from rich.prompt import Prompt, Confirm

PYPROJECT_TOML = Path(__file__).parent.parent / "pyproject.toml"
VERSION_RE = re.compile('^version = "(.*)"$')

with PYPROJECT_TOML.open("r") as f:
    pyproject_toml_lines = f.readlines()

current_version = None
for line in pyproject_toml_lines:
    if match := VERSION_RE.fullmatch(line.strip()):
        current_version = match.group(1)
        break

assert current_version is not None

print("Current version: ", current_version)
new_version = Prompt.ask("New version: ")

with PYPROJECT_TOML.open("w") as f:
    for line in pyproject_toml_lines:
        if match := VERSION_RE.fullmatch(line.strip()):
            f.write(f'version = "{new_version}"\n')
        else:
            f.write(line)

subprocess.check_call(["uv", "lock"])
subprocess.check_call(["git", "add", "pyproject.toml", "uv.lock"])
subprocess.check_call(["git", "diff", "--cached"])
if not Confirm.ask("Accept diff?"):
    sys.exit(1)
subprocess.check_call(["git", "commit", "-m", f"Update version to {new_version}"])
subprocess.check_call(["git", "push"])
subprocess.check_call(["git", "tag", new_version])
subprocess.check_call(["git", "push", "--tags"])
subprocess.check_call(
    [
        "gh",
        "release",
        "create",
        new_version,
        "--notes",
        "",
    ]
)
