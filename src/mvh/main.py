import argparse
import logging
import sys

import uvicorn
from pydantic import ValidationError
from rich.logging import RichHandler

from mvh.api import webhook_app, set_settings
from mvh.deploy import deploy, bootstrap
from mvh.schema import (
    AppSettings,
    generate_webhook_id,
)

logging.basicConfig(format="%(message)s", level=logging.DEBUG, handlers=[RichHandler()])
_logger = logging.getLogger(__name__)


def new_webhook(_settings: AppSettings):
    print(generate_webhook_id())


def build_settings_override(args: argparse.Namespace):
    overrides: dict[str, str] = {}
    for k in AppSettings.model_fields:
        if (v := getattr(args, k, None)) is not None:
            overrides[k] = v
    return overrides


def run_api(settings: AppSettings):
    set_settings(settings)
    uvicorn.run(webhook_app, host="0.0.0.0", port=8000, log_config=None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--remote-url",
        default=None,
        type=str,
        help="URL of git remote git repository (env: MVH_REMOTE_URL)",
    )
    parser.add_argument(
        "--branch",
        default=None,
        type=str,
        help="Name of git branch to use (default: 'main') (env: MVH_BRANCH)",
    )
    parser.add_argument(
        "--node",
        default=None,
        type=str,
        help="Name of the node to deploy for (env: MVH_NODE)",
    )
    subparsers = parser.add_subparsers(required=True)

    deploy_parser = subparsers.add_parser("deploy")
    deploy_parser.set_defaults(func=deploy)

    bootstrap_parser = subparsers.add_parser("bootstrap")
    bootstrap_parser.set_defaults(func=bootstrap)

    new_webhook_parser = subparsers.add_parser("new-webhook")
    new_webhook_parser.set_defaults(func=new_webhook)

    api_parser = subparsers.add_parser("api")
    api_parser.set_defaults(func=run_api)

    args = parser.parse_args()
    overrides = build_settings_override(args)

    try:
        settings = AppSettings(**overrides)
    except ValidationError as ex:
        should_raise = False
        for error in ex.errors():
            if error["type"] == "missing":
                _logger.error("Field required: %s", ".".join(error["loc"]))
            else:
                should_raise = True

        if should_raise:
            raise
        parser.print_help()
        return 1

    args.func(settings)
    return 0


if __name__ == "__main__":
    sys.exit(main())
