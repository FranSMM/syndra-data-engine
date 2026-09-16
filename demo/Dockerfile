# Python 3.12 rather than the 3.11 the backend pins: this app has been running
# on 3.12 in Streamlit Cloud for months (its runtime.txt says so), and moving it
# in-house is not the moment to also change the interpreter under it. The
# divergence is deliberate and costs nothing: the two services share no code.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Requirements first so the dependency layer caches independently of the app.
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# The app resolves assets relative to the working directory
# (st.image("assets/...")), so that layout has to survive into the image.
COPY .streamlit/config.toml /app/.streamlit/config.toml
COPY assets /app/assets
COPY syndra_demo_app.py /app/

# secrets.toml is deliberately NOT copied. It is bind-mounted read-only at
# /app/.streamlit/secrets.toml by infra/docker-compose.prod.yml. Anything baked
# into a layer stays extractable with `docker history` even if a later layer
# deletes it, and rotating the demo key would otherwise mean rebuilding and
# re-pushing the image instead of editing one line on the VPS.

# Run as a non-root user: this is the only publicly reachable container on the
# box. UID 1000 is not arbitrary: it matches the `syndra` user on the VPS that
# owns the 0600 secrets file, so the read-only bind mount stays readable inside
# the container without loosening its permissions on the host.
RUN useradd --uid 1000 --create-home --shell /usr/sbin/nologin demo \
    && chown -R demo:demo /app
USER demo

EXPOSE 8501

# Streamlit answers this endpoint once the server is serving. curl is absent
# from the slim image, so the probe is issued from Python.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=4).status == 200 else 1)"

CMD ["streamlit", "run", "syndra_demo_app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true"]
