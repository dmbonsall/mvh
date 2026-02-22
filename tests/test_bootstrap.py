import contextlib
import os
import shutil
import subprocess
from pathlib import Path

import pytest


@contextlib.contextmanager
def cd(path: str):
    old_dir = os.getcwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_dir)


@pytest.fixture(autouse=True, scope="session")
def docker():
    subprocess.check_call(["docker", "ps"])


@pytest.fixture(autouse=True, scope="session")
def docker_build(docker):
    subprocess.check_call(["docker", "build", "-t", "mvh-test:latest", "."])


@pytest.fixture(autouse=True, scope="session")
def stacks_repo() -> Path:
    if Path("/tmp/mvh-test/test-stacks-repo").exists():
        shutil.rmtree("/tmp/mvh-test/test-stacks-repo")
    Path("/tmp/mvh-test").mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        Path(__file__).parent / "test-stacks-repo",
        Path("/tmp/mvh-test/test-stacks-repo"),
    )
    with cd("/tmp/mvh-test/test-stacks-repo"):
        subprocess.check_call(["git", "init"])
        subprocess.check_call(["git", "branch", "-M", "main"])
        subprocess.check_call(["git", "add", "--all"])
        subprocess.check_call(["git", "commit", "-m", "Initial commit"])

    return Path("/tmp/mvh-test/test-stacks-repo")


def mvh_stack_running() -> bool:
    result = subprocess.run(
        ["docker", "ps", "--filter=name=mvh-mvh-1", "--format=json"],
        capture_output=True,
    )
    assert result.returncode == 0
    lines = result.stdout.decode("utf-8").strip().split("\n")
    return len(lines) == 1


@pytest.fixture(autouse=True)
def cleanup_mvh_stack():
    if mvh_stack_running():
        subprocess.check_call(["docker", "stop", "mvh-mvh-1"])
        subprocess.check_call(["docker", "rm", "mvh-mvh-1"])


def test_bootstrap(stacks_repo):
    subprocess.check_call(
        [
            "docker",
            "run",
            "--rm",
            "--volume=/var/run/docker.sock:/var/run/docker.sock",
            "--volume=/tmp/mvh-test/test-stacks-repo:/test-stacks-repo",
            "--env=REMOTE_URL=file:///test-stacks-repo",
            "--env=BRANCH=main",
            "--env=HOSTNAME=pytest",
            "mvh-test:latest",
            "bootstrap",
        ]
    )
    assert mvh_stack_running()
