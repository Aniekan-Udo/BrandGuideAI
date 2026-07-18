# Start everything

docker compose up -d

# Check logs

docker compose logs -f api

docker compose logs -f worker_generation

# Monitor Celery tasks

open http://localhost:5555  # Flower dashboard

# Scale generation workers

docker compose up -d --scale worker_generation=3

