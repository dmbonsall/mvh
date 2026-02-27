import argparse
import functools
import logging
import sys
from typing import Callable

import uvicorn
from pydantic import ValidationError
from rich.console import Console

from mvh.api import webhook_app, set_settings
from mvh.deploy import deploy, bootstrap
from mvh.schema import (
    AppSettings,
    generate_webhook_id,
)

# Console is really just intended for immediate feedback from the CLI, use logging
# otherwise.
console = Console()

logging.basicConfig(
    format="%(asctime)s %(name)-12s %(levelname)-8s %(message)s", level=logging.DEBUG
)


def new_webhook(_settings: AppSettings):
    console.print(generate_webhook_id(), style="cyan")


def build_settings_override(args: argparse.Namespace):
    overrides: dict[str, str] = {}
    for k in AppSettings.model_fields:
        if (v := getattr(args, k, None)) is not None:
            overrides[k] = v
    return overrides


def run_api(settings: AppSettings):
    set_settings(settings)
    uvicorn.run(webhook_app, host="0.0.0.0", port=8000, log_config=None)


def requires_settings(
    func: Callable[[AppSettings], int | None],
) -> Callable[[argparse.Namespace], int]:
    @functools.wraps(func)
    def wrapper(args: argparse.Namespace) -> int:
        overrides = build_settings_override(args)

        try:
            settings = AppSettings(**overrides)
        except ValidationError as ex:
            for error in ex.errors():
                if error["type"] == "missing":
                    console.print(
                        "Field required:",
                        ".".join(str(loc) for loc in error["loc"]),
                        style="bold red",
                    )
                else:
                    raise

            return 64
        return func(settings) or 0

    return wrapper


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
    deploy_parser.set_defaults(func=requires_settings(deploy))

    bootstrap_parser = subparsers.add_parser("bootstrap")
    bootstrap_parser.set_defaults(func=requires_settings(bootstrap))

    api_parser = subparsers.add_parser("api")
    api_parser.set_defaults(func=requires_settings(run_api))

    new_webhook_parser = subparsers.add_parser("new-webhook")
    new_webhook_parser.set_defaults(func=new_webhook)

    args = parser.parse_args()

    rc = args.func(args)
    if rc == 64:
        parser.print_help()
    return rc


if __name__ == "__main__":
    sys.exit(main())
