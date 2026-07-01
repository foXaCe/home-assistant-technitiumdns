"""Home Assistant helpers for the technitiumdns-api AsyncClient."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers import aiohttp_client

# The technitiumdns-api client library has the same top-level name as this
# custom component; mypy's flat module resolution (no `custom_components`
# package marker) resolves the bare "technitiumdns" name to this integration
# instead of the installed library, hence the attr-defined false positive.
from technitiumdns import AsyncClient  # type: ignore[attr-defined]

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


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
