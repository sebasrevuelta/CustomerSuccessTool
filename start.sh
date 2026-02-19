docker build -t customer-success-tool .
docker run --rm -p 5001:5000 -p 5432:5432 \
  --env-file .env \
  -e POSTGRES_DB=customer_success \
  -e POSTGRES_USER=appuser \
  -e POSTGRES_PASSWORD=app_password \
  -v "$(pwd)/credentials.json:/app/credentials.json:ro" \
  customer-success-tool