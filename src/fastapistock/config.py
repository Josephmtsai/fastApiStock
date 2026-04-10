"""Application settings loaded from environment variables via python-dotenv."""

import os

from dotenv import load_dotenv

load_dotenv()

REDIS_HOST: str = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT: int = int(os.getenv('REDIS_PORT', '6379'))
REDIS_PASSWORD: str | None = os.getenv('REDIS_PASSWORD') or None
TELEGRAM_TOKEN: str = os.getenv('TELEGRAM_TOKEN', '')
TELEGRAM_USER_ID: str = os.getenv('TELEGRAM_USER_ID', '')
GOOGLE_SHEETS_ID: str = os.getenv('GOOGLE_SHEETS_ID', '')
GOOGLE_SHEETS_PORTFOLIO_GID: str = os.getenv('GOOGLE_SHEETS_PORTFOLIO_GID', '')
GOOGLE_SHEETS_PORTFOLIO_GID_TW: str = os.getenv(
    'GOOGLE_SHEETS_PORTFOLIO_GID_TW', GOOGLE_SHEETS_PORTFOLIO_GID
)
GOOGLE_SHEETS_PORTFOLIO_GID_US: str = os.getenv('GOOGLE_SHEETS_PORTFOLIO_GID_US', '')
GOOGLE_SHEETS_INVESTMENT_PLAN_GID: str = os.getenv(
    'GOOGLE_SHEETS_INVESTMENT_PLAN_GID', ''
)
TELEGRAM_WEBHOOK_SECRET: str = os.getenv('TELEGRAM_WEBHOOK_SECRET', '')
PORTFOLIO_CACHE_TTL: int = int(os.getenv('PORTFOLIO_CACHE_TTL', '3600'))


def tw_stock_codes() -> list[str]:
    """Parse TW_STOCKS env var into a list of Taiwan stock codes.

    Returns:
        List of non-empty stripped stock code strings.
    """
    raw = os.getenv('TW_STOCKS', '')
    return [c.strip() for c in raw.split(',') if c.strip()]


def us_stock_symbols() -> list[str]:
    """Parse US_STOCKS env var into a list of uppercased US stock tickers.

    Returns:
        List of non-empty uppercased ticker strings.
    """
    raw = os.getenv('US_STOCKS', '')
    return [s.strip().upper() for s in raw.split(',') if s.strip()]


def redis_url() -> str:
    """Build the Redis connection URL for the rate-limiter storage backend.

    Returns:
        Redis URI string compatible with the ``limits`` library,
        including credentials when ``REDIS_PASSWORD`` is set.
    """
    if REDIS_PASSWORD:
        return f'redis://:{REDIS_PASSWORD}@{REDIS_HOST}:{REDIS_PORT}'
    return f'redis://{REDIS_HOST}:{REDIS_PORT}'
