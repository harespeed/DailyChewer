FROM python:3.11-slim

ARG USE_CHINA_MIRROR=true
ARG APT_MIRROR=https://mirrors.tuna.tsinghua.edu.cn/debian
ARG PIP_INDEX_URL=https://mirrors.tuna.tsinghua.edu.cn/pypi/web/simple
ARG PIP_TRUSTED_HOST=mirrors.tuna.tsinghua.edu.cn

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Optionally switch Debian and pip to mainland China mirrors for faster builds.
RUN if [ "${USE_CHINA_MIRROR}" = "true" ]; then \
        if [ -f /etc/apt/sources.list.d/debian.sources ]; then \
            sed -i "s|http://deb.debian.org/debian|${APT_MIRROR}|g; s|https://deb.debian.org/debian|${APT_MIRROR}|g; s|http://security.debian.org/debian-security|${APT_MIRROR}|g; s|https://security.debian.org/debian-security|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources; \
        fi; \
        if [ -f /etc/apt/sources.list ]; then \
            sed -i "s|http://deb.debian.org/debian|${APT_MIRROR}|g; s|https://deb.debian.org/debian|${APT_MIRROR}|g; s|http://security.debian.org/debian-security|${APT_MIRROR}|g; s|https://security.debian.org/debian-security|${APT_MIRROR}|g" /etc/apt/sources.list; \
        fi; \
        pip config set global.index-url "${PIP_INDEX_URL}"; \
        pip config set global.trusted-host "${PIP_TRUSTED_HOST}"; \
    else \
        pip config unset global.index-url || true; \
        pip config unset global.trusted-host || true; \
    fi

# Install minimal system packages required by pandas/openpyxl/python-docx workflows.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        libxml2 \
        libxslt1.1 \
        zlib1g \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md alembic.ini ./
COPY backend ./backend
COPY cli ./cli
COPY dailychewer ./dailychewer
COPY tests ./tests

# Install Python dependencies with the configured mirror when enabled.
RUN pip install --upgrade pip \
    && if [ "${USE_CHINA_MIRROR}" = "true" ]; then \
        pip install -i "${PIP_INDEX_URL}" --trusted-host "${PIP_TRUSTED_HOST}" -e .; \
    else \
        pip install -e .; \
    fi

RUN mkdir -p /app/data /app/input /app/frontend

ENTRYPOINT ["dailychewer"]
CMD ["--help"]
