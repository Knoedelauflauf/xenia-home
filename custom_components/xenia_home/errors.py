"""Turn failed requests to the machine into translated Home Assistant errors."""

from collections.abc import AsyncIterator, Coroutine
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from aiohttp import ClientError
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import UpdateFailed

from .const import XENIA_DOMAIN

if TYPE_CHECKING:
    from .coordinator import XeniaCoordinator

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


async def async_write(
    coordinator: XeniaCoordinator[Any], command: Coroutine[Any, Any, None]
) -> None:
    """Send a command, then poll the machine a second later, even after a failure."""
    try:
        async with machine_write():
            await command
    finally:
        coordinator.async_refresh_after_command()
