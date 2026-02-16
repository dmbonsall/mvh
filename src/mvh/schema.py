import logging
import random
import string
from typing import Annotated

from pydantic import BaseModel, AfterValidator, Field
from pydantic_settings import BaseSettings

_docker_logger = logging.getLogger("docker-compose")

WEBHOOK_CHARS = string.ascii_letters + string.digits


def generate_webhook_id() -> str:
    return "".join(random.choices(WEBHOOK_CHARS, k=64))


def validate_webhook_ids(val: list[str]) -> list[str]:
    for val in val:
        validate_webhook_id(val)
    return val


def validate_webhook_id(val: str) -> str:
    if not all(c in WEBHOOK_CHARS for c in val):
        raise ValueError(f"Invalid webhook id {val}")
    return val


class AppSettings(BaseSettings):
    remote_url: str = "/Users/david/projects/docker-compose"
    branch: str = "master"
    hostname: str = "aquarius"
    webhook_ids: Annotated[
        list[str], AfterValidator(validate_webhook_ids), Field(default_factory=list)
    ]


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
            _docker_logger.log(
                logging.getLevelNamesMapping()[self.level.upper()], self.msg
            )
        elif self.id and self.status:
            _docker_logger.info("%s %s", self.id, self.status)
