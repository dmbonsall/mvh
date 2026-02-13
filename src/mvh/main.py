import logging
import os
import subprocess
import tempfile
from pathlib import Path

import yaml
from pydantic import BaseModel
from pydantic_settings import BaseSettings
from rich.logging import RichHandler

logging.basicConfig(level=logging.DEBUG, handlers=[RichHandler()])
_logger = logging.getLogger(__name__)


class AppSettings(BaseSettings):
    repo_remote_url: str = "/Users/david/projects/docker-compose"
    default_branch: str = "master"
    hostname: str = "aquarius"


class HostConfig(BaseModel):
    stacks: list[str]


class RepoConfig(BaseModel):
    hosts: dict[str, HostConfig]


settings = AppSettings()


def git(*args):
    subprocess.check_call(["git", *args])


def docker_compose(*args):
    subprocess.check_call(["docker", "compose", *args])


def main():
    directory = Path(tempfile.gettempdir()) / "mvh"
    if not (directory / ".git").is_dir():
        _logger.info("Cloning repo %s", settings.repo_remote_url)
        git("clone", settings.repo_remote_url, directory)
    assert (directory / ".git").is_dir(), "not a git repo"

    os.chdir(directory)
    git("checkout", settings.default_branch)
    git("pull", "origin", settings.default_branch)

    assert (directory / "mvh-config.yaml").is_file(), "missing mvh-config.yaml"
    with (directory / "mvh-config.yaml").open(encoding="utf-8") as f:
        repo_config = RepoConfig.model_validate(yaml.safe_load(f))

    if settings.hostname not in repo_config.hosts:
        _logger.warning("Host not found in repo config, nothing to do")
        return

    for stack in repo_config.hosts[settings.hostname].stacks:
        _logger.info("Processing stack %s", stack)
        assert (directory / stack).is_dir(), f"{stack} is not a directory"
        os.chdir(directory / stack)
        docker_compose("up", "--detach")


if __name__ == "__main__":
    main()
