import logging
import os
import socket
import subprocess
import tempfile
from pathlib import Path

import yaml

from mvh.schema import DockerComposeLogLine, NodeConfig, AppSettings, RepoConfig

_logger = logging.getLogger(__name__)


def git(*args):
    res = subprocess.run(["git", *args], capture_output=True)
    stderr = res.stderr.decode("utf-8")
    assert res.returncode == 0, stderr


def docker_compose(*args):
    proc = subprocess.Popen(
        ["docker", "compose", "--ansi=never", "--progress=json", *args],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    for line in proc.stdout:
        DockerComposeLogLine.model_validate_json(line).log()

    proc.poll()
    assert proc.returncode == 0


def duplicate_self(settings: AppSettings):
    r = subprocess.run(
        ["docker", "ps", "--format", "{{ .ID}} {{ .Image}}"], capture_output=True
    )
    assert r.returncode == 0
    image = None
    for line in r.stdout.decode("utf-8").splitlines():
        if line.startswith(socket.gethostname()):
            image = line.split(" ", 1)[1]
            break
    assert image is not None

    args = [
        "docker",
        "run",
        "--detach",
        "--env",
        f"MVH_REMOTE_URL={settings.remote_url}",
        "--env",
        f"MVH_BRANCH={settings.branch}",
        "--env",
        f"MVH_NODE={settings.node}",
        "--volume",
        "/var/run/docker.sock:/var/run/docker.sock",
        image,
        "bootstrap",
    ]
    _logger.info("Duplicating stack %s", args)
    r = subprocess.run(args, capture_output=True)
    assert r.returncode == 0


def setup_git_repo(local_repo: Path, remote_url: str, branch: str):
    _logger.info("Setting up git repo")
    if not (local_repo / ".git").is_dir():
        _logger.info("Cloning repo %s", remote_url)
        git("clone", remote_url, local_repo)
    assert (local_repo / ".git").is_dir(), "not a git repo"

    os.chdir(local_repo)
    git("checkout", branch)
    git("pull", "origin", branch)
    _logger.info("Updated git repo to latest version")


def _deploy_all_stacks_for_host(
    local_repo: Path,
    host_config: NodeConfig,
    settings: AppSettings,
):
    should_bootstrap = False
    for stack in host_config.stacks:
        if stack == host_config.mvh_stack:
            should_bootstrap = True
            continue

        _deploy_single_stack(local_repo, stack)

    if should_bootstrap:
        duplicate_self(settings)


def _deploy_single_stack(local_repo: Path, stack: str):
    _logger.info("Processing stack %s", stack)
    assert (local_repo / stack).is_dir(), f"{stack} is not a directory"
    os.chdir(local_repo / stack)
    docker_compose("down")
    docker_compose("up", "--detach", "--force-recreate")


def _prepare_repo(settings: AppSettings) -> tuple[Path, RepoConfig]:
    local_repo = Path(tempfile.gettempdir()) / "mvh"
    setup_git_repo(local_repo, settings.remote_url, settings.branch)

    assert (local_repo / "mvh-config.yaml").is_file(), "missing mvh-config.yaml"
    with (local_repo / "mvh-config.yaml").open(encoding="utf-8") as f:
        repo_config = RepoConfig.model_validate(yaml.safe_load(f))

    if settings.node not in repo_config.nodes:
        _logger.warning("Node not found in repo config, nothing to do")
        raise ValueError(f"Node not found in repo config: {settings.node}")
    return local_repo, repo_config


def deploy(settings: AppSettings):
    local_repo, repo_config = _prepare_repo(settings)
    _deploy_all_stacks_for_host(
        local_repo,
        repo_config.nodes[settings.node],
        settings,
    )


def bootstrap(settings: AppSettings):
    local_repo, repo_config = _prepare_repo(settings)
    _deploy_single_stack(local_repo, repo_config.nodes[settings.node].mvh_stack)
