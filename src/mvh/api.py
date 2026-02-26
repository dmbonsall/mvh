from http import HTTPStatus
from fastapi import FastAPI, Depends, HTTPException

from mvh.deploy import deploy
from mvh.schema import AppSettings

__settings: AppSettings | None = None


def get_settings() -> AppSettings:
    if __settings is None:
        raise RuntimeError("Dependencies not set, problem with initialization")
    return __settings


def set_settings(settings: AppSettings):
    global __settings
    __settings = settings


webhook_app = FastAPI()


@webhook_app.get("/")
async def root():
    return {"status": "ok"}


@webhook_app.post("/webhook/{webhook_id}")
async def webhook(webhook_id: str, settings: AppSettings = Depends(get_settings)):
    if webhook_id not in settings.webhook_ids:
        raise HTTPException(status_code=HTTPStatus.NOT_FOUND)

    deploy(settings)
    return {"status": "ok"}
