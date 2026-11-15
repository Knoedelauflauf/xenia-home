"""Tests for the config and options flows."""

from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.xenia_home.config_flow import CREATE_NEW_SCRIPT
from custom_components.xenia_home.const import (
    CONF_MANAGED_SCRIPT_ID,
    CONF_WEIGHT_MANAGEMENT_ENABLED,
    CONF_WEIGHT_MAX,
    CONF_WEIGHT_MIN,
    CONF_WEIGHT_STEP,
    DEFAULT_SCRIPT_NAME,
    XENIA_DOMAIN,
)

from tests.conftest import MockXeniaApi

WEIGHT_SETTINGS = {CONF_WEIGHT_MIN: 20.0, CONF_WEIGHT_MAX: 45.0, CONF_WEIGHT_STEP: 0.1}


async def test_user_flow_creates_entry(
    hass: HomeAssistant, mock_xenia_api: MockXeniaApi
) -> None:
    """The machine is added under its host and keyed on its MAC address."""
    result = await hass.config_entries.flow.async_init(
        XENIA_DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: " xenia.local "}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "xenia.local"
    assert result["data"] == {CONF_HOST: "xenia.local"}
    assert result["result"].unique_id == "aa:bb:cc:dd:ee:ff"


@pytest.mark.parametrize(
    "fault",
    [
        {"exc": TimeoutError()},
        {"exc": OSError("refused")},
        {"json": {"NOT_A_XENIA": 1}},
    ],
)
async def test_user_flow_recovers_from_cannot_connect(
    hass: HomeAssistant,
    mock_xenia_api: MockXeniaApi,
    fault: dict,
) -> None:
    """An unreachable host or another device shows an error until the host works."""
    mock_xenia_api.for_host("bad.host").override("get", "overview_single", **fault)
    result = await hass.config_entries.flow.async_init(
        XENIA_DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "bad.host"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "xenia.local"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_aborts_when_already_configured(
    hass: HomeAssistant,
    mock_xenia_api: MockXeniaApi,
    mock_config_entry: MockConfigEntry,
) -> None:
    """A machine can only be added once."""
    mock_config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        XENIA_DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "xenia.local"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_updates_the_host_of_a_known_machine(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
) -> None:
    """Adding a machine again under a new host moves the existing entry there."""
    new_machine = mock_xenia_api.for_host("192.168.1.20")
    entities = {
        e.unique_id: e.entity_id
        for e in er.async_entries_for_config_entry(
            entity_registry, init_integration.entry_id
        )
    }

    result = await hass.config_entries.flow.async_init(
        XENIA_DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "192.168.1.20"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
    assert hass.config_entries.async_entries(XENIA_DOMAIN) == [init_integration]
    assert init_integration.data == {CONF_HOST: "192.168.1.20"}
    assert init_integration.state is ConfigEntryState.LOADED
    assert new_machine.bodies("get", "overview")
    assert {
        e.unique_id: e.entity_id
        for e in er.async_entries_for_config_entry(
            entity_registry, init_integration.entry_id
        )
    } == entities


async def test_reconfigure_changes_host_and_keeps_entities(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
) -> None:
    """A new host reloads the entry; devices and entities stay the same."""
    new_machine = mock_xenia_api.for_host("new.host")
    entities = {
        e.unique_id: e.entity_id
        for e in er.async_entries_for_config_entry(
            entity_registry, init_integration.entry_id
        )
    }

    result = await init_integration.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "  new.host  "}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert init_integration.data == {CONF_HOST: "new.host"}
    assert init_integration.state is ConfigEntryState.LOADED
    assert new_machine.bodies("get", "overview_single")
    assert {
        e.unique_id: e.entity_id
        for e in er.async_entries_for_config_entry(
            entity_registry, init_integration.entry_id
        )
    } == entities


async def test_reconfigure_recovers_from_cannot_connect(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_xenia_api: MockXeniaApi
) -> None:
    """An unreachable host shows an error and leaves the entry unchanged."""
    mock_xenia_api.for_host("bad.host").override(
        "get", "overview_single", exc=OSError()
    )
    mock_xenia_api.for_host("new.host")
    result = await init_integration.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "bad.host"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    assert init_integration.data == {CONF_HOST: "xenia.local"}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "new.host"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"


async def test_reconfigure_rejects_another_machine(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_xenia_api: MockXeniaApi
) -> None:
    """A host that answers with another machine leaves the entry unchanged."""
    mock_xenia_api.for_host("other.host").set_overview_single(
        MA_MAC="11:22:33:44:55:66"
    )
    result = await init_integration.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HOST: "other.host"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "unique_id_mismatch"
    assert init_integration.data == {CONF_HOST: "xenia.local"}
    assert init_integration.unique_id == "aa:bb:cc:dd:ee:ff"


async def _start_weight_options(hass: HomeAssistant, entry: MockConfigEntry) -> dict:
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_WEIGHT_MANAGEMENT_ENABLED: True}
    )


async def test_options_enable_weight_management(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_xenia_api: MockXeniaApi
) -> None:
    """Picking a weight script and a range adds the weight target number."""
    mock_xenia_api.set_script(10, "1;13;27 45;7;", "MyShot")
    result = await _start_weight_options(hass, init_integration)
    assert result["step_id"] == "select_script"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MANAGED_SCRIPT_ID: "10"}
    )
    assert result["step_id"] == "configure_weight"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], WEIGHT_SETTINGS
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert init_integration.options == {
        CONF_WEIGHT_MANAGEMENT_ENABLED: True,
        CONF_MANAGED_SCRIPT_ID: 10,
        **WEIGHT_SETTINGS,
    }
    state = hass.states.get("number.xenia_espresso_machine_script_weight_target")
    assert state is not None
    assert float(state.state) == 45.0


async def test_options_offer_only_scripts_with_a_weight_target(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_xenia_api: MockXeniaApi
) -> None:
    """Scripts without a weight command, or unreadable ones, are not offered."""
    mock_xenia_api.set_scripts(
        {10: "WithWeight", 20: "NoWeight", 30: "Unreadable", 40: "Malformed"}
    )
    mock_xenia_api.set_script(10, "1;13;27 45;7;", "WithWeight")
    mock_xenia_api.set_script(20, "1;13;7;", "NoWeight")
    mock_xenia_api.set_script(40, "1;x;27 45;7;", "Malformed")
    result = await _start_weight_options(hass, init_integration)

    selector = result["data_schema"].schema[CONF_MANAGED_SCRIPT_ID]
    assert selector.config["options"] == [
        {"value": CREATE_NEW_SCRIPT, "label": DEFAULT_SCRIPT_NAME},
        {"value": "10", "label": "WithWeight"},
    ]


async def test_options_create_new_script(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_xenia_api: MockXeniaApi
) -> None:
    """A new weight script is created on the machine and managed."""
    result = await _start_weight_options(hass, init_integration)
    mock_xenia_api.set_scripts({25: DEFAULT_SCRIPT_NAME})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MANAGED_SCRIPT_ID: CREATE_NEW_SCRIPT}
    )
    assert result["step_id"] == "configure_weight"
    assert mock_xenia_api.bodies("post", "scripts/create") == [
        '{"script_id":null,"Edit":"Disabled","switch":null,"script":"none",'
        '"name":"HA Espresso","instruction":"1;13;3 70 5000;12 5000;27 40;17;7;"}'
    ]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], WEIGHT_SETTINGS
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert init_integration.options[CONF_MANAGED_SCRIPT_ID] == 25


async def test_options_create_new_script_next_to_one_of_the_same_name(
    hass: HomeAssistant, init_integration: MockConfigEntry, mock_xenia_api: MockXeniaApi
) -> None:
    """A script of the default name that existed before is not taken over."""
    mock_xenia_api.set_scripts({12: DEFAULT_SCRIPT_NAME})
    result = await _start_weight_options(hass, init_integration)
    mock_xenia_api.set_scripts({12: DEFAULT_SCRIPT_NAME, 26: DEFAULT_SCRIPT_NAME})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MANAGED_SCRIPT_ID: CREATE_NEW_SCRIPT}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], WEIGHT_SETTINGS
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert init_integration.options[CONF_MANAGED_SCRIPT_ID] == 26


@pytest.mark.parametrize(
    ("settings", "errors"),
    [
        (
            {CONF_WEIGHT_MIN: 50.0, CONF_WEIGHT_MAX: 25.0, CONF_WEIGHT_STEP: 0.5},
            {CONF_WEIGHT_MAX: "weight_max_not_above_min"},
        ),
        (
            {CONF_WEIGHT_MIN: 30.0, CONF_WEIGHT_MAX: 30.0, CONF_WEIGHT_STEP: 0.0},
            {
                CONF_WEIGHT_MAX: "weight_max_not_above_min",
                CONF_WEIGHT_STEP: "weight_step_not_positive",
            },
        ),
    ],
)
async def test_options_reject_an_unusable_weight_range(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    settings: dict[str, float],
    errors: dict[str, str],
) -> None:
    """An empty range or a step of zero is shown as an error and can be fixed."""
    mock_xenia_api.set_script(10, "1;13;27 45;7;", "MyShot")
    result = await _start_weight_options(hass, init_integration)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MANAGED_SCRIPT_ID: "10"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], settings
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == errors

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], WEIGHT_SETTINGS
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert init_integration.options == {
        CONF_WEIGHT_MANAGEMENT_ENABLED: True,
        CONF_MANAGED_SCRIPT_ID: 10,
        **WEIGHT_SETTINGS,
    }


async def test_options_abort_when_created_script_is_missing(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The flow aborts when the machine does not list the created script."""
    result = await _start_weight_options(hass, init_integration)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MANAGED_SCRIPT_ID: CREATE_NEW_SCRIPT}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "script_not_created"


@pytest.mark.parametrize(
    ("method", "path", "choice"),
    [
        ("get", "scripts/list", None),
        ("post", "scripts/create", CREATE_NEW_SCRIPT),
    ],
)
async def test_options_abort_when_machine_unreachable(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_xenia_api: MockXeniaApi,
    method: str,
    path: str,
    choice: str | None,
) -> None:
    """A failed request to the machine aborts the flow."""
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    if choice is not None:
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_WEIGHT_MANAGEMENT_ENABLED: True}
        )
    mock_xenia_api.fail(method, path)
    user_input = (
        {CONF_WEIGHT_MANAGEMENT_ENABLED: True}
        if choice is None
        else {CONF_MANAGED_SCRIPT_ID: choice}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], user_input
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "cannot_connect"


async def test_options_disable_weight_management(
    hass: HomeAssistant,
    mock_xenia_api: MockXeniaApi,
    mock_config_entry_factory_with_options,
) -> None:
    """Turning weight management off removes the weight target number."""
    mock_xenia_api.set_script(10, "1;13;27 45;7;", "MyShot")
    entry = mock_config_entry_factory_with_options(
        {CONF_WEIGHT_MANAGEMENT_ENABLED: True, CONF_MANAGED_SCRIPT_ID: 10}
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    weight = "number.xenia_espresso_machine_script_weight_target"
    assert hass.states.get(weight) is not None

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_WEIGHT_MANAGEMENT_ENABLED: False}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        CONF_WEIGHT_MANAGEMENT_ENABLED: False,
        CONF_MANAGED_SCRIPT_ID: None,
    }
    assert hass.states.get(weight) is None
