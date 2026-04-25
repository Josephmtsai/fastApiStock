release: uv run alembic upgrade head
web: uvicorn src.fastapistock.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips='*'
