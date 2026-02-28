import contextlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

import pytest
import requests
import yaml


@contextlib.contextmanager
def cd(path: str | Path):
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
def _stacks_repo() -> Path:
    if Path("/tmp/mvh-test").exists():
        shutil.rmtree("/tmp/mvh-test")
    Path("/tmp/mvh-test").mkdir(parents=True)
    Path("/tmp/mvh-test/test-stacks-repo.git").mkdir(parents=True)
    with cd("/tmp/mvh-test/test-stacks-repo.git"):
        subprocess.check_call(["git", "init", "--bare"])
        shutil.move("hooks/post-update.sample", "hooks/post-update")

    shutil.copytree(
        Path(__file__).parent / "test-stacks-repo",
        Path("/tmp/mvh-test/test-stacks-repo"),
    )
    with cd("/tmp/mvh-test/test-stacks-repo"):
        subprocess.check_call(["git", "init"])
        subprocess.check_call(["git", "branch", "-M", "main"])
        subprocess.check_call(["git", "add", "--all"])
        subprocess.check_call(["git", "commit", "-m", "Initial commit"])
        subprocess.check_call(
            ["git", "remote", "add", "origin", "/tmp/mvh-test/test-stacks-repo.git"]
        )
        subprocess.check_call(["git", "push", "-u", "origin", "main"])
        # shutil.move(".git/hooks/post-update.sample", ".git/hooks/post-update")
        subprocess.check_call(["git", "branch", "test"])
        subprocess.check_call(["git", "push", "-u", "origin", "test"])

    server_proc = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "http.server",
            "-d",
            "/tmp/mvh-test",
            "-b",
            "127.0.0.1",
            "8001",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    yield Path("/tmp/mvh-test/test-stacks-repo")
    server_proc.terminate()


@pytest.fixture(autouse=True)
def stacks_repo(_stacks_repo) -> Path:
    with cd(_stacks_repo):
        subprocess.check_call(["git", "checkout", "test"])
        subprocess.check_call(["git", "reset", "--hard", "main"])
        subprocess.check_call(["git", "push", "origin", "test", "--force"])

    return _stacks_repo


def stack_running(name: str) -> bool:
    result = subprocess.run(
        ["docker", "ps", f"--filter=name={name}", "--format=json"],
        capture_output=True,
    )
    assert result.returncode == 0
    lines = [line for line in result.stdout.decode("utf-8").strip().split("\n") if line]
    return len(lines) == 1


def mvh_stack_running() -> bool:
    return stack_running("mvh-mvh-1")


def mvh_labels() -> dict[str, str]:
    result = subprocess.run(
        ["docker", "ps", "--filter=name=mvh-mvh-1", "--format=json"],
        capture_output=True,
    )
    assert result.returncode == 0
    lines = result.stdout.decode("utf-8").strip().split("\n")
    assert len(lines) == 1
    data = json.loads(lines[0])
    tokens = data["Labels"].split(",")
    return {(kv := t.split("="))[0]: (kv[1] if len(kv) > 1 else None) for t in tokens}


@pytest.fixture()
def deploy_mvh(stacks_repo) -> Callable[[], None]:
    def _deploy():
        with cd(stacks_repo / "mvh"):
            subprocess.check_call(["docker", "compose", "run", "mvh", "deploy"])
            time.sleep(1)  # wait for mvh to start serving
        assert mvh_stack_running()

    return _deploy


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
            "--env=MVH_REMOTE_URL=http://host.docker.internal:8001/test-stacks-repo.git",
            "--env=MVH_BRANCH=test",
            "--env=MVH_NODE=pytest",
            "mvh-test:latest",
            "bootstrap",
        ]
    )
    assert mvh_stack_running()


def test_webhook_with_bootstrap(stacks_repo):
    with cd(stacks_repo / "mvh"):
        subprocess.check_call(["docker", "compose", "up", "-d"])
        time.sleep(1)  # wait for mvh to start serving
        with open("docker-compose.yaml", "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        data["services"]["mvh"]["labels"] = {"test.extra": "EXTRA"}
        with open("docker-compose.yaml", "w", encoding="utf-8") as f:
            yaml.dump(data, f)
        subprocess.check_call(["git", "commit", "-am", "Update labels"])
        subprocess.check_call(["git", "push", "origin", "test"])

    res = requests.post("http://localhost:8000/webhook/abc123", timeout=15)
    time.sleep(5)  # wait for the restart
    assert res.status_code == 200
    assert mvh_stack_running()
    assert mvh_labels()["test.extra"] == "EXTRA"


def test_build_with_deploy(stacks_repo, deploy_mvh):
    deploy_mvh()
    assert stack_running("my-custom-my_custom_service-1")

    with cd(stacks_repo / "my-custom"):
        result = subprocess.run(
            ["docker", "compose", "exec", "my_custom_service", "cat", "/test-file"],
            capture_output=True,
        )
    assert result.returncode == 0
    assert result.stdout.decode("utf-8").strip() == "Before changes..."

    with cd(stacks_repo / "my-custom"):
        assert (
            Path("test-file").read_text(encoding="utf-8").strip() == "Before changes..."
        )
        Path("test-file").write_text("After changes...\n", encoding="utf-8")
        subprocess.check_call(["git", "commit", "-am", "Update test-file"])
        subprocess.check_call(["git", "push", "origin", "test"])

    deploy_mvh()
    assert stack_running("my-custom-my_custom_service-1")
    with cd(stacks_repo / "my-custom"):
        result = subprocess.run(
            ["docker", "compose", "exec", "my_custom_service", "cat", "/test-file"],
            capture_output=True,
        )
    assert result.returncode == 0
    assert result.stdout.decode("utf-8").strip() == "After changes..."
