FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends postgresql postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install -r /app/requirements.txt

COPY app.py /app/app.py
COPY app_common.py /app/app_common.py
COPY auth_oidc.py /app/auth_oidc.py
COPY dashboard_page.py /app/dashboard_page.py
COPY feature_requests_page.py /app/feature_requests_page.py
COPY trends_page.py /app/trends_page.py
COPY settings_page.py /app/settings_page.py
COPY nurture.py /app/nurture.py
COPY nurture_customer_success.py /app/nurture_customer_success.py
COPY nurture_feature_request.py /app/nurture_feature_request.py
COPY templates /app/templates
COPY customer_success_schema.sql /app/customer_success_schema.sql
COPY customer_success_sample_data.sql /app/customer_success_sample_data.sql
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

EXPOSE 5000
EXPOSE 5432

CMD ["/app/docker-entrypoint.sh"]
