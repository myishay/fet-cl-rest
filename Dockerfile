# syntax=docker/dockerfile:1

# ---------------------------------------------------------------------------
# Stage 1: build fet-cl from upstream source, CLI-only (no GUI Qt deps).
# FET is AGPL-3.0; we build the UNMODIFIED upstream source. See NOTICE.
# ---------------------------------------------------------------------------
FROM debian:bookworm-slim AS fet-build

ARG FET_VERSION=7.8.6
ARG FET_TARBALL=fet-${FET_VERSION}.tar.xz
ARG FET_URL=https://lalescu.ro/liviu/fet/download/${FET_TARBALL}

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        curl \
        xz-utils \
        qtbase5-dev \
        qt5-qmake \
        qtbase5-dev-tools \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
RUN curl -fL "${FET_URL}" -o "${FET_TARBALL}" \
    && tar -xf "${FET_TARBALL}" \
    && mv "fet-${FET_VERSION}" fet

# Build with the Qt5 qmake toolchain. This compiles both `fet` (GUI) and the
# `fet-cl` CLI; we install only fet-cl. (The COMMAND_LINE_ONLY flag is a no-op
# for this .pro, but the resulting fet-cl links only libQt5Core at runtime —
# verified with ldd — so the runtime image needs just libqt5core5a, no GUI/X11.)
WORKDIR /build/fet
RUN qmake fet.pro \
    && make -j"$(nproc)" \
    && (install -Dm755 fet-cl /out/usr/local/bin/fet-cl \
        || install -Dm755 src/fet-cl /out/usr/local/bin/fet-cl)

# ---------------------------------------------------------------------------
# Stage 2: runtime — Python API + the fet-cl binary.
# ---------------------------------------------------------------------------
FROM python:3.12-slim-bookworm AS runtime

# Runtime libs fet-cl needs (Qt5 core, no GUI/X11).
RUN apt-get update && apt-get install -y --no-install-recommends \
        libqt5core5a \
    && rm -rf /var/lib/apt/lists/*

COPY --from=fet-build /out/usr/local/bin/fet-cl /usr/local/bin/fet-cl

WORKDIR /srv
COPY pyproject.toml README.md NOTICE ./
COPY app ./app

RUN pip install --no-cache-dir .

# Non-root runtime user; jobs dir must be writable.
ENV FETREST_JOBS_DIR=/var/lib/fet-cl-rest/jobs \
    FETREST_FET_CL_BINARY=/usr/local/bin/fet-cl \
    PYTHONUNBUFFERED=1
RUN useradd --system --create-home --uid 10001 fet \
    && mkdir -p "${FETREST_JOBS_DIR}" \
    && chown -R fet:fet "${FETREST_JOBS_DIR}"
USER fet

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz').status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
