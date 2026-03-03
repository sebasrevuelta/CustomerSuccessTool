FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app/src

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql postgresql-client sudo \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY src /app/src
COPY templates /app/templates
COPY sql/customer_success_schema.sql /app/sql/customer_success_schema.sql
COPY sql/customer_success_sample_data.sql /app/sql/customer_success_sample_data.sql
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 5000
EXPOSE 5432

RUN useradd -m appuser
RUN chown -R appuser:appuser /app
RUN echo "appuser ALL=(ALL) NOPASSWD: /usr/bin/pg_ctlcluster, /usr/bin/pg_isready, /usr/bin/psql" > /etc/sudoers.d/appuser \
    && chmod 440 /etc/sudoers.d/appuser
USER appuser

CMD ["/app/docker-entrypoint.sh"]
