# Architecture

High-level overview of how the TechnitiumDNS integration is structured.

## Data flow

```
Technitium DNS Server  ──HTTP──▶  technitiumdns-api (PyPI client)
                                        │
                                        ▼
                          client.py (create_api_client)
                                        │
                                        ▼
                 __init__.py  (ConfigEntry setup, unique_id migration,
                               platform forwarding, services)
                                        │
        ┌───────────────┬───────────────┼───────────────┬───────────────┐
        ▼               ▼               ▼               ▼               ▼
    sensor.py       switch.py        button.py     device_tracker.py   (services.yaml)
  DNS statistics   ad-blocking    temp-disable      DHCP devices       cleanup_devices,
                     toggle         buttons        + diagnostics       get_dhcp_leases
```

## Modules

| File | Responsibility |
| --- | --- |
| `__init__.py` | Entry setup/unload, `unique_id` migration, platform forwarding, service registration |
| `config_flow.py` | UI configuration and options flow (`CONFIG_VERSION` migrations) |
| `client.py` | Thin wrapper building the `technitiumdns-api` client |
| `const.py` | Domain constants, defaults, keys |
| `sensor.py` | DNS statistics and per-device diagnostic sensors |
| `switch.py` | Ad-blocking enable/disable, reflecting effective server state |
| `button.py` | Temporary ad-blocking disable buttons (5/10/30/60 min, 1 day) |
| `device_tracker.py` | DHCP-based device trackers with IP filtering |
| `activity_analyzer.py` | Smart activity scoring (distinguishes real usage from background traffic) |
| `dns_logs.py` | DNS query-log retrieval (when a logging DNS app is available) |
| `utils.py` | Helpers (e.g. MAC normalization) |

## Entities & registries

- Entities are keyed by stable `unique_id`s; `__init__.py` migrates legacy ids and resolves
  duplicates on startup.
- Device trackers and their diagnostic sensors are created/removed dynamically as devices
  join/leave the network or as IP filters change.

## Services

- `technitiumdns.cleanup_devices` — remove orphaned device-tracker entities and sensors.
- `technitiumdns.get_dhcp_leases` — retrieve DHCP lease information programmatically.

## External dependency

The integration relies on the [`technitiumdns-api`](https://pypi.org/project/technitiumdns-api/)
package, installed automatically by Home Assistant from `manifest.json` `requirements`.
