import logging
import os
import subprocess
import tempfile
from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from rich.logging import RichHandler

logging.basicConfig(format="%(message)s", level=logging.DEBUG, handlers=[RichHandler()])
_logger = logging.getLogger(__name__)


class AppSettings(BaseSettings):
    repo_remote_url: str = "/Users/david/projects/docker-compose"
    default_branch: str = "master"
    hostname: str = "aquarius"


class HostConfig(BaseModel):
    stacks: list[str]


class RepoConfig(BaseModel):
    hosts: dict[str, HostConfig]


class DockerComposeLogLine(BaseModel):
    level: str | None = None
    msg: str | None = None
    id: str | None = None
    status: str | None = None

    def log(self):
        if self.level and self.msg:
            _logger.log(logging.getLevelNamesMapping()[self.level.upper()], self.msg)
        elif self.id and self.status:
            _logger.info("%s %s", self.id, self.status)


settings = AppSettings()


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


def setup_git_repo(local_repo: Path):
    _logger.info("Setting up git repo")
    if not (local_repo / ".git").is_dir():
        _logger.info("Cloning repo %s", settings.repo_remote_url)
        git("clone", settings.repo_remote_url, local_repo)
    assert (local_repo / ".git").is_dir(), "not a git repo"

    os.chdir(local_repo)
    git("checkout", settings.default_branch)
    git("pull", "origin", settings.default_branch)
    _logger.info("Updated git repo to latest version")


def deploy_stacks(local_repo: Path, repo_config: RepoConfig):
    for stack in repo_config.hosts[settings.hostname].stacks:
        _logger.info("Processing stack %s", stack)
        assert (local_repo / stack).is_dir(), f"{stack} is not a directory"
        os.chdir(local_repo / stack)
        docker_compose("up", "--detach")


def main():
    local_repo = Path(tempfile.gettempdir()) / "mvh"
    setup_git_repo(local_repo)

    assert (local_repo / "mvh-config.yaml").is_file(), "missing mvh-config.yaml"
    with (local_repo / "mvh-config.yaml").open(encoding="utf-8") as f:
        repo_config = RepoConfig.model_validate(yaml.safe_load(f))

    if settings.hostname not in repo_config.hosts:
        _logger.warning("Host not found in repo config, nothing to do")
        return

    deploy_stacks(local_repo, repo_config)


if __name__ == "__main__":
    main()
