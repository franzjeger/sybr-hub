# Supported container target: Linux amd64, Python 3.14. Base pinned by digest.
FROM python:3.14-slim-bookworm@sha256:48b13b003dda20b16f9442b8475aa05fe21bf6579a8c881db92ffb4d8fd20f83 AS builder
WORKDIR /src
COPY requirements.lock .
RUN python -m venv /opt/venv && /opt/venv/bin/pip install --require-hashes -r requirements.lock
RUN python -m pip install build==1.6.1 setuptools==84.0.0 setuptools-scm==9.2.2 wheel==0.48.0
COPY . .
ARG RELEASE_VERSION=0.0.0.dev0
RUN SETUPTOOLS_SCM_PRETEND_VERSION=${RELEASE_VERSION} python -m build --wheel --no-isolation --outdir /wheels \
    && /opt/venv/bin/pip install --no-deps /wheels/*.whl

FROM python:3.14-slim-bookworm@sha256:48b13b003dda20b16f9442b8475aa05fe21bf6579a8c881db92ffb4d8fd20f83
ARG SOURCE_REVISION=unknown
LABEL org.opencontainers.image.source="https://github.com/franzjeger/sybr-hub" \
      org.opencontainers.image.revision="${SOURCE_REVISION}"
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl chromium fonts-dejavu-core libpango-1.0-0 libpangoft2-1.0-0 \
    libicu72 libssl3 libgssapi-krb5-2 libunwind8 openssh-client \
    && rm -rf /var/lib/apt/lists/*
RUN test "$(uname -m)" = x86_64 \
    && curl --fail --location --retry 3 https://github.com/PowerShell/PowerShell/releases/download/v7.6.5/powershell-7.6.5-linux-x64.tar.gz -o /tmp/pwsh.tar.gz \
    && echo 'b34ab3b19acac1d3d4d0d3cfdb02acf62f457b0b6a962ff008132033f7566844  /tmp/pwsh.tar.gz' | sha256sum --check \
    && mkdir -p /opt/powershell \
    && tar -xzf /tmp/pwsh.tar.gz -C /opt/powershell \
    && chmod +x /opt/powershell/pwsh \
    && ln -s /opt/powershell/pwsh /usr/local/bin/pwsh \
    && rm /tmp/pwsh.tar.gz \
    && pwsh -NoProfile -Command '$PSVersionTable.PSVersion.ToString()'
COPY --from=builder /opt/venv /opt/venv
COPY scripts/grant_write.py scripts/reconcile_finding.py scripts/purge_customer.py /opt/sybr-ops/
RUN useradd --uid 10001 --create-home --home-dir /var/lib/sybr sybr
USER 10001:10001
WORKDIR /var/lib/sybr
ENV PATH="/opt/venv/bin:$PATH" PYTHONDONTWRITEBYTECODE=1 \
    MSP_DATA_DIR=/var/lib/sybr/data MSP_CONFIG_DIR=/var/lib/sybr/config \
    MSP_AUDIT_DIR=/var/lib/sybr/audits SYBR_BUILD_COMMIT=${SOURCE_REVISION} \
    SYBR_KEY_WRAP_SECRET_FILE=/run/secrets/key_wrap_secret
EXPOSE 8099
RUN python -c "from weasyprint import HTML; assert HTML(string='<p>Sybr package smoke</p>').write_pdf().startswith(b'%PDF')"
HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8099/api/ready', timeout=4)"
CMD ["sybr-hub"]
