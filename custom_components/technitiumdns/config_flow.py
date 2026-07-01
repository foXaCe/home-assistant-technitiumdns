"""Config flow for TechnitiumDNS integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector
import voluptuous as vol

# The technitiumdns-api client library has the same top-level name as this
# custom component; mypy's flat module resolution (no `custom_components`
# package marker) resolves the bare "technitiumdns" name to this integration
# instead of the installed library, hence the attr-defined false positive.
from technitiumdns import (  # type: ignore[attr-defined]
    InvalidTokenError,
    TransportError,
)

from .client import create_api_client
from .const import (
    ACTIVITY_ANALYSIS_WINDOWS,
    ACTIVITY_SCORE_THRESHOLDS,
    CONF_ACTIVITY_ANALYSIS_WINDOW,
    CONF_ACTIVITY_SCORE_THRESHOLD,
    CONF_DHCP_LOG_TRACKING,
    CONF_DHCP_SMART_ACTIVITY,
    CONF_DHCP_STALE_THRESHOLD,
    CONF_STATS_UPDATE_INTERVAL,
    DEFAULT_ACTIVITY_ANALYSIS_WINDOW,
    DEFAULT_ACTIVITY_SCORE_THRESHOLD,
    DEFAULT_DHCP_LOG_TRACKING,
    DEFAULT_DHCP_SMART_ACTIVITY,
    DEFAULT_DHCP_STALE_THRESHOLD,
    DEFAULT_STATS_UPDATE_INTERVAL,
    DHCP_IP_FILTER_MODES,
    DHCP_STALE_THRESHOLD_OPTIONS,
    DHCP_UPDATE_INTERVAL_OPTIONS,
    DOMAIN,
    STATS_DURATION_API,
    STATS_DURATION_OPTIONS,
    STATS_UPDATE_INTERVAL_OPTIONS,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from homeassistant.config_entries import ConfigFlowResult

CONFIG_VERSION = 7

_LOGGER = logging.getLogger(__name__)


def _int_select(
    options: Iterable[int], translation_key: str
) -> selector.SelectSelector:
    """Build a translatable dropdown for a list of integer choices.

    The option values are stored as strings (Home Assistant selectors are
    string-based); read them back through ``int(...)``.
    """
    return selector.SelectSelector(
        selector.SelectSelectorConfig(
            options=[str(option) for option in options],
            translation_key=translation_key,
        )
    )


@config_entries.HANDLERS.register(DOMAIN)
class TechnitiumDNSConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for TechnitiumDNS."""

    VERSION = CONFIG_VERSION

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        """Get the options flow for this handler."""
        return TechnitiumDNSOptionsFlowHandler()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                api = await create_api_client(
                    self.hass,
                    api_url=user_input["api_url"],
                    token=user_input["token"],
                    check_ssl=user_input["check_ssl"],
                    cluster_mode=user_input.get("cluster_mode", False),
                )
                await api.dashboard.stats(
                    type=STATS_DURATION_API.get(
                        user_input["stats_duration"], user_input["stats_duration"]
                    ),
                    utc=True,
                )

                return self.async_create_entry(
                    title=user_input["server_name"], data=user_input
                )
            except InvalidTokenError:
                errors["base"] = "auth"
            except TransportError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during config flow")
                errors["base"] = "unknown"

        data_schema = vol.Schema(
            {
                vol.Required("api_url"): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.URL,
                    )
                ),
                vol.Required("check_ssl", default=True): selector.BooleanSelector(),
                vol.Optional("cluster_mode", default=False): selector.BooleanSelector(),
                vol.Required("token"): selector.TextSelector(
                    selector.TextSelectorConfig(
                        type=selector.TextSelectorType.PASSWORD,
                    )
                ),
                vol.Required("server_name"): selector.TextSelector(),
                vol.Required("username"): selector.TextSelector(),
                vol.Required("stats_duration"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=STATS_DURATION_OPTIONS,
                        translation_key="stats_duration",
                    )
                ),
            }
        )

        return self.async_show_form(
            step_id="user", data_schema=data_schema, errors=errors
        )

    async def async_step_import(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle import from config migration."""
        return await self.async_step_user(user_input)

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Handle re-authentication after an invalid token."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Prompt for a new API token and validate it."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()

        if user_input is not None:
            try:
                api = await create_api_client(
                    self.hass,
                    api_url=reauth_entry.data["api_url"],
                    token=user_input["token"],
                    check_ssl=reauth_entry.data.get("check_ssl", True),
                    cluster_mode=reauth_entry.data.get("cluster_mode", False),
                )
                await api.dashboard.stats(
                    type=STATS_DURATION_API.get(
                        reauth_entry.data["stats_duration"],
                        reauth_entry.data["stats_duration"],
                    ),
                    utc=True,
                )
            except InvalidTokenError:
                errors["base"] = "auth"
            except TransportError:
                errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("Unexpected error during reauth")
                errors["base"] = "unknown"
            else:
                return self.async_update_reload_and_abort(
                    reauth_entry, data_updates={"token": user_input["token"]}
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required("token"): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD,
                        )
                    ),
                }
            ),
            description_placeholders={"name": reauth_entry.title},
            errors=errors,
        )


class TechnitiumDNSOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle an options flow for TechnitiumDNS."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            if user_input.get("test_dhcp"):
                return await self.async_step_dhcp_test()

            data_to_save = {k: v for k, v in user_input.items() if k != "test_dhcp"}
            return self.async_create_entry(title="", data=data_to_save)

        options_schema = vol.Schema(
            {
                vol.Optional(
                    "enable_dhcp_tracking",
                    default=self.config_entry.options.get(
                        "enable_dhcp_tracking", False
                    ),
                ): bool,
                vol.Optional(
                    "dhcp_update_interval",
                    default=str(
                        self.config_entry.options.get("dhcp_update_interval", 60)
                    ),
                ): _int_select(DHCP_UPDATE_INTERVAL_OPTIONS, "dhcp_update_interval"),
                vol.Optional(
                    CONF_STATS_UPDATE_INTERVAL,
                    default=str(
                        self.config_entry.options.get(
                            CONF_STATS_UPDATE_INTERVAL, DEFAULT_STATS_UPDATE_INTERVAL
                        )
                    ),
                ): _int_select(STATS_UPDATE_INTERVAL_OPTIONS, "stats_update_interval"),
                vol.Optional(
                    "dhcp_ip_filter_mode",
                    default=self.config_entry.options.get(
                        "dhcp_ip_filter_mode", "disabled"
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=list(DHCP_IP_FILTER_MODES.keys()),
                        translation_key="dhcp_ip_filter_mode",
                    )
                ),
                vol.Optional(
                    "dhcp_ip_ranges",
                    default=self.config_entry.options.get("dhcp_ip_ranges", ""),
                ): str,
                vol.Optional(
                    CONF_DHCP_LOG_TRACKING,
                    default=self.config_entry.options.get(
                        CONF_DHCP_LOG_TRACKING, DEFAULT_DHCP_LOG_TRACKING
                    ),
                ): bool,
                vol.Optional(
                    CONF_DHCP_STALE_THRESHOLD,
                    default=str(
                        self.config_entry.options.get(
                            CONF_DHCP_STALE_THRESHOLD, DEFAULT_DHCP_STALE_THRESHOLD
                        )
                    ),
                ): _int_select(
                    list(DHCP_STALE_THRESHOLD_OPTIONS.keys()), "dhcp_stale_threshold"
                ),
                vol.Optional(
                    CONF_DHCP_SMART_ACTIVITY,
                    default=self.config_entry.options.get(
                        CONF_DHCP_SMART_ACTIVITY, DEFAULT_DHCP_SMART_ACTIVITY
                    ),
                ): bool,
                vol.Optional(
                    CONF_ACTIVITY_SCORE_THRESHOLD,
                    default=str(
                        self.config_entry.options.get(
                            CONF_ACTIVITY_SCORE_THRESHOLD,
                            DEFAULT_ACTIVITY_SCORE_THRESHOLD,
                        )
                    ),
                ): _int_select(
                    list(ACTIVITY_SCORE_THRESHOLDS.keys()), "activity_score_threshold"
                ),
                vol.Optional(
                    CONF_ACTIVITY_ANALYSIS_WINDOW,
                    default=str(
                        self.config_entry.options.get(
                            CONF_ACTIVITY_ANALYSIS_WINDOW,
                            DEFAULT_ACTIVITY_ANALYSIS_WINDOW,
                        )
                    ),
                ): _int_select(
                    list(ACTIVITY_ANALYSIS_WINDOWS.keys()), "activity_analysis_window"
                ),
                vol.Optional("test_dhcp", default=False): bool,
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=options_schema,
        )

    async def async_step_dhcp_test(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Test DHCP connection and display results."""
        if user_input is not None:
            return await self.async_step_init()

        errors: dict[str, str] = {}
        dhcp_results = ""

        try:
            config_data = self.config_entry.data
            api = await create_api_client(
                self.hass,
                api_url=config_data["api_url"],
                token=config_data["token"],
                check_ssl=config_data.get("check_ssl", True),
                cluster_mode=config_data.get("cluster_mode", False),
            )
            leases = await api.dhcp.leases_list()

            if leases:
                dhcp_results = (
                    f"✅ Successfully retrieved {len(leases)} DHCP leases:\n\n"
                )
                for i, lease in enumerate(leases[:20], 1):
                    dhcp_results += f"Device {i}:\n"
                    dhcp_results += f"  IP: {lease.address or 'N/A'}\n"
                    dhcp_results += f"  MAC: {lease.hardware_address or 'N/A'}\n"
                    dhcp_results += f"  Hostname: {lease.host_name or 'N/A'}\n"
                    dhcp_results += f"  Type: {lease.type or 'N/A'}\n"
                    dhcp_results += f"  Status: {lease.address_status or 'N/A'}\n"
                    dhcp_results += f"  Scope: {lease.scope or 'N/A'}\n"
                    if lease.lease_expires:
                        dhcp_results += f"  Expires: {lease.lease_expires}\n"
                    dhcp_results += "\n"

                if len(leases) > 20:
                    dhcp_results += f"... and {len(leases) - 20} more leases\n"
            else:
                dhcp_results = (
                    "✅ DHCP API connection successful, but no leases found.\n\n"
                    "This could mean:\n"
                    "- No devices are currently connected\n"
                    "- DHCP server is not configured\n"
                    "- DHCP scope is empty"
                )

        except Exception as err:
            dhcp_results = (
                f"❌ Failed to retrieve DHCP leases:\n\nError: {err}\n\n"
                "Please check:\n"
                "- Technitium DNS server is running\n"
                "- API URL is correct\n"
                "- Token has DHCP access permissions\n"
                "- DHCP server is enabled in Technitium"
            )
            errors["base"] = "dhcp_connection_failed"

        test_schema = vol.Schema(
            {
                vol.Optional("dhcp_test_results", default=dhcp_results): str,
            }
        )

        return self.async_show_form(
            step_id="dhcp_test",
            data_schema=test_schema,
            errors=errors,
            description_placeholders={"test_results": dhcp_results},
        )
