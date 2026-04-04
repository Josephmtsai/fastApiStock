"""Application settings loaded from environment variables via python-dotenv."""

import os

from dotenv import load_dotenv

load_dotenv()

REDIS_HOST: str = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT: int = int(os.getenv('REDIS_PORT', '6379'))
REDIS_PASSWORD: str | None = os.getenv('REDIS_PASSWORD') or None


def redis_url() -> str:
    """Build the Redis connection URL for the rate-limiter storage backend.

    Returns:
        Redis URI string compatible with the ``limits`` library,
        including credentials when ``REDIS_PASSWORD`` is set.
    """
    if REDIS_PASSWORD:
        return f'redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}'
    return f'redis://{REDIS_HOST}:{REDIS_PORT}'
