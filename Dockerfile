FROM ghcr.io/astral-sh/uv:0.10-python3.14-alpine AS base

RUN apk add docker-cli docker-cli-compose git

ENV UV_COMPILE_BYTECODE=1 UV_NO_DEV=1 UV_LINK_MODE=copy

# Change the working directory to the `app` directory
WORKDIR /app

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project

# Copy the project into the image
COPY . /app

# Sync the project
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked

ENTRYPOINT ["uv", "run", "--no-sync", "mvh"]
CMD ["api"]