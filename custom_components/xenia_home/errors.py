"""Turn failed requests to the machine into translated Home Assistant errors."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from aiohttp import ClientError
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import XENIA_DOMAIN

REQUEST_ERRORS = (ClientError, OSError, TimeoutError)


def describe_error(err: BaseException) -> str:
    """Return the class name and message; str(TimeoutError()) alone is empty."""
    message = str(err)
    return f"{type(err).__name__}: {message}" if message else type(err).__name__


def update_failed(err: BaseException) -> UpdateFailed:
    """Return a translated UpdateFailed for a failed read from the machine."""
    return UpdateFailed(
        translation_domain=XENIA_DOMAIN,
        translation_key="update_failed",
        translation_placeholders={"error": describe_error(err)},
    )


@asynccontextmanager
async def machine_write() -> AsyncIterator[None]:
    """Raise a translated HomeAssistantError when a write to the machine fails."""
    try:
        yield
    except REQUEST_ERRORS as err:
        raise HomeAssistantError(
            translation_domain=XENIA_DOMAIN,
            translation_key="write_failed",
            translation_placeholders={"error": describe_error(err)},
        ) from err
