"""Home Assistant helpers for the technitiumdns-api AsyncClient."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import aiohttp_client

from technitiumdns import AsyncClient


async def create_api_client(
    hass: HomeAssistant,
    *,
    api_url: str,
    token: str,
    check_ssl: bool = True,
    cluster_mode: bool = False,
) -> AsyncClient:
    """Create an AsyncClient using Home Assistant's pooled aiohttp session."""
    session = aiohttp_client.async_get_clientsession(hass, verify_ssl=check_ssl)
    # The pooled session is injected directly, so the client never has to open
    # (or later clean up) a session of its own.
    return AsyncClient(
        api_url,
        token=token,
        session=session,
        node="cluster" if cluster_mode else None,
    )
