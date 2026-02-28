import logging
import random
import string
from typing import Annotated

from pydantic import BaseModel, AfterValidator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

_docker_logger = logging.getLogger("docker-compose")

WEBHOOK_CHARS = string.ascii_letters + string.digits


def generate_webhook_id() -> str:
    return "".join(random.choices(WEBHOOK_CHARS, k=64))


def validate_webhook_ids(val: list[str]) -> list[str]:
    for webhook_id in val:
        validate_webhook_id(webhook_id)
    return val


def validate_webhook_id(val: str) -> str:
    if not all(c in WEBHOOK_CHARS for c in val):
        raise ValueError(f"Invalid webhook id {val}")
    return val


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="mvh_")

    remote_url: str
    branch: str = "main"
    node: str
    webhook_ids: Annotated[
        list[str], AfterValidator(validate_webhook_ids), Field(default_factory=list)
    ]


class StackConfig(BaseModel):
    path: str
    is_mvh: bool = False
    build: bool = False


class NodeConfig(BaseModel):
    stacks: list[StackConfig]

    @property
    def mvh_stack(self) -> StackConfig | None:
        result = list(filter(lambda x: x.is_mvh, self.stacks))
        if not result:
            return None
        return result[0]


class RepoConfig(BaseModel):
    nodes: dict[str, NodeConfig]
