"""Shared response envelope schema used by all API endpoints."""

from typing import Generic, Literal, TypeVar

from pydantic import BaseModel

T = TypeVar('T')


class ResponseEnvelope(BaseModel, Generic[T]):
    """Standard API response wrapper.

    All endpoints return this envelope so consumers can write
    predictable parsing logic regardless of the domain.

    Attributes:
        status: 'success' on 2xx, 'error' on 4xx/5xx.
        data: Domain payload; None on error responses.
        message: Human-readable detail; empty string on success.
    """

    status: Literal['success', 'error']
    data: T | None = None
    message: str = ''
