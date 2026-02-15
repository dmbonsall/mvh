import logging
import os
import subprocess
import tempfile
from pathlib import Path

import yaml

from mvh.schema import DockerComposeLogLine, HostConfig, AppSettings, RepoConfig

_logger = logging.getLogger(__name__)


def git(*args):
    subprocess.run(["git", *args], capture_output=True)


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


def deploy_stacks(local_repo: Path, host_config: HostConfig):
    for stack in host_config.stacks:
        _logger.info("Processing stack %s", stack)
        assert (local_repo / stack).is_dir(), f"{stack} is not a directory"
        os.chdir(local_repo / stack)
        docker_compose("up", "--detach")


def deploy(settings: AppSettings):
    local_repo = Path(tempfile.gettempdir()) / "mvh"
    setup_git_repo(local_repo, settings.remote_url, settings.branch)

    assert (local_repo / "mvh-config.yaml").is_file(), "missing mvh-config.yaml"
    with (local_repo / "mvh-config.yaml").open(encoding="utf-8") as f:
        repo_config = RepoConfig.model_validate(yaml.safe_load(f))

    if settings.hostname not in repo_config.hosts:
        _logger.warning("Host not found in repo config, nothing to do")
        return

    deploy_stacks(local_repo, repo_config.hosts[settings.hostname])
