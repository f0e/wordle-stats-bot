FROM python:3.13-slim-bookworm
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential libpq-dev gcc python3-dev libxml2-dev libxslt1-dev git && \
    rm -rf /var/lib/apt/lists/*

ADD . /app

WORKDIR /app
RUN uv sync --locked

CMD ["uv", "run", "bot"]
