# Quality scale

Tracks compliance with the [Home Assistant integration quality scale](https://contributors.home-assistant.io/core/quality-scale/). A box is only checked once a rule has been verified against its official documentation. Exempt rules name the reason the rule gives for the exemption.

## Bronze
- [x] `action-setup` - Service actions are registered in async_setup
- [x] `appropriate-polling` - If it's a polling integration, set an appropriate polling interval
- [ ] `brands` - Has branding assets available for the integration. The icon ships in `brand/`, which Home Assistant and HACS use for custom integrations; the rule asks for the brands repository, which only takes core integrations.
- [x] `common-modules` - Place common patterns in common modules
- [x] `config-flow-test-coverage` - Full test coverage for the config flow
- [x] `config-flow` - Integration needs to be able to be set up via the UI
    - [x] Uses `data_description` to give context to fields
    - [x] Uses `ConfigEntry.data` and `ConfigEntry.options` correctly
- [x] `dependency-transparency` - Exempt: the integration has no external dependency.
- [x] `docs-actions` - The documentation describes the provided service actions that can be used
- [x] `docs-conditions` - Exempt: the integration provides no conditions.
- [x] `docs-high-level-description` - The documentation includes a high-level description of the integration brand, product, or service
- [x] `docs-installation-instructions` - The documentation provides step-by-step installation instructions for the integration, including, if needed, prerequisites
- [x] `docs-removal-instructions` - The documentation provides removal instructions
- [x] `docs-triggers` - Exempt: the integration provides no triggers.
- [x] `entity-event-setup` - Entity events are subscribed in the correct lifecycle methods
- [x] `entity-unique-id` - Entities have a unique ID
- [x] `has-entity-name` - Entities use has_entity_name = True
- [x] `runtime-data` - Use ConfigEntry.runtime_data to store runtime data
- [x] `test-before-configure` - Test a connection in the config flow
- [x] `test-before-setup` - Check during integration initialization if we are able to set it up correctly
- [x] `unique-config-entry` - Don't allow the same device or service to be able to be set up twice

## Silver
- [x] `action-exceptions` - Service actions raise exceptions when encountering failures
- [x] `config-entry-unloading` - Support config entry unloading
- [x] `docs-configuration-parameters` - The documentation describes all integration configuration options
- [x] `docs-installation-parameters` - The documentation describes all integration installation parameters
- [x] `entity-unavailable` - Mark entity unavailable if appropriate
- [x] `integration-owner` - Has an integration owner
- [x] `log-when-unavailable` - If internet/device/service is unavailable, log once when unavailable and once when back connected. The coordinators log through Home Assistant; a managed script that cannot be read is logged once and once when it is back.
- [x] `parallel-updates` - Number of parallel updates is specified
- [x] `reauthentication-flow` - Exempt: the machine needs no authentication.
- [x] `test-coverage` - Above 95% test coverage for all integration modules

## Gold
- [x] `devices` - The integration creates devices
- [x] `diagnostics` - Implements diagnostics
- [x] `discovery-update-info` - Integration uses discovery info to update network information. DHCP of a registered machine updates a host given as IP address; a host name is kept, since it resolves to the new address.
- [ ] `discovery` - Devices can be discovered. DHCP only follows machines set up already; whether the machine announces an mDNS service has not been checked yet.
- [x] `docs-data-update` - The documentation describes how data is updated
- [ ] `docs-examples` - The documentation provides automation examples the user can use. There are the shot timer blueprint and the scale tare automation; common cases like heating up on a schedule or turning off after idling are missing.
- [x] `docs-known-limitations` - The documentation describes known limitations of the integration (not to be confused with bugs)
- [ ] `docs-supported-devices` - The documentation describes known supported / unsupported devices. The README names the tested DBL but not how to recognize API v2 or which firmware is needed.
- [x] `docs-supported-functions` - The documentation describes the supported functionality, including entities, and platforms
- [x] `docs-troubleshooting` - The documentation provides troubleshooting information
- [ ] `docs-use-cases` - The documentation describes use cases to illustrate how this integration can be used. The introduction lists features; a section with use cases is missing.
- [x] `dynamic-devices` - Exempt: one fixed device per config entry.
- [x] `entity-category` - Entities are assigned an appropriate EntityCategory
- [x] `entity-device-class` - Entities use device classes where possible
- [x] `entity-disabled-by-default` - Integration disables less popular (or noisy) entities
- [x] `entity-translations` - Entities have translated names
- [x] `exception-translations` - Exception messages are translatable
- [x] `icon-translations` - Entities implement icon translations
- [x] `reconfiguration-flow` - Integrations should have a reconfigure flow
- [x] `repair-issues` - Repair issues and repair flows are used when user intervention is needed
- [x] `stale-devices` - Exempt: one fixed device per config entry.

## Platinum
- [x] `async-dependency` - Exempt: the integration has no external dependency; the in-tree client is async throughout (aiohttp).
- [x] `inject-websession` - The machine client takes the session Home Assistant provides
- [ ] `strict-typing` - Strict typing. mypy checks the integration with the strict settings of Home Assistant Core; the rule also asks for a listing in core's `.strict-typing`, which a custom integration cannot have.
