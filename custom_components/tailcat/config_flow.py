"""Config flow and options flow for Tailcat, sharing the same wizard steps."""
from __future__ import annotations

import asyncio
import os
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigFlow, OptionsFlow
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult
from homeassistant.helpers import selector

from .const import (
    CONF_ALLOW_NODEKEY,
    CONF_BINARY_PATH,
    CONF_ENABLED,
    CONF_KEY_MODE,
    CONF_KEY_NAME,
    CONF_MODE,
    CONF_NAME,
    CONF_PORT,
    CONF_REGION,
    CONF_RISK_CONFIRM,
    DEFAULT_BINARY_PATH,
    DEFAULT_REGION,
    DOMAIN,
    KEY_MODE_EPHEMERAL,
    KEY_MODE_SAVED,
    KEY_MODES,
    MODE_PORT,
    MODES,
    RISKY_MODES,
)

BINARY_CHECK_TIMEOUT = 5


async def async_validate_binary(path: str) -> str | None:
    """Return an error code if `path` does not look like a runnable tailcat binary."""
    if not os.path.isfile(path):
        return "binary_not_found"
    if not os.access(path, os.X_OK):
        return "binary_not_executable"

    try:
        process = await asyncio.create_subprocess_exec(
            path,
            "genkey",
            "--list",
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(process.wait(), timeout=BINARY_CHECK_TIMEOUT)
    except OSError:
        return "binary_not_executable"
    except asyncio.TimeoutError:
        return "binary_timeout"
    return None


class _TailcatFlowMixin:
    """Wizard steps shared by the config flow and the options flow."""

    draft: dict[str, Any]

    def _step_defaults(self) -> dict[str, Any]:
        raise NotImplementedError

    async def _async_finish(self) -> FlowResult:
        raise NotImplementedError

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if not hasattr(self, "draft"):
            self.draft = self._step_defaults()

        errors: dict[str, str] = {}
        if user_input is not None:
            error = await async_validate_binary(user_input[CONF_BINARY_PATH])
            if error:
                errors[CONF_BINARY_PATH] = error
            else:
                self.draft.update(user_input)
                return await self.async_step_mode()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_NAME, default=self.draft.get(CONF_NAME, "")
                ): str,
                vol.Required(
                    CONF_BINARY_PATH,
                    default=self.draft.get(CONF_BINARY_PATH, DEFAULT_BINARY_PATH),
                ): str,
            }
        )
        return self.async_show_form(
            step_id="user", data_schema=schema, errors=errors
        )

    async def async_step_mode(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self.draft.update(user_input)
            if user_input[CONF_MODE] == MODE_PORT:
                return await self.async_step_port()
            if user_input[CONF_MODE] in RISKY_MODES:
                return await self.async_step_risk_confirm()
            return await self.async_step_key()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_MODE, default=self.draft.get(CONF_MODE, MODE_PORT)
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=MODES,
                        translation_key="mode",
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
            }
        )
        return self.async_show_form(step_id="mode", data_schema=schema)

    async def async_step_port(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self.draft.update(user_input)
            return await self.async_step_key()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PORT, default=self.draft.get(CONF_PORT, 8123)
                ): vol.All(vol.Coerce(int), vol.Range(min=1, max=65535)),
            }
        )
        return self.async_show_form(step_id="port", data_schema=schema)

    async def async_step_risk_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input[CONF_RISK_CONFIRM]:
                errors[CONF_RISK_CONFIRM] = "risk_not_confirmed"
            else:
                self.draft.update(user_input)
                return await self.async_step_key()

        schema = vol.Schema({vol.Required(CONF_RISK_CONFIRM, default=False): bool})
        return self.async_show_form(
            step_id="risk_confirm",
            data_schema=schema,
            errors=errors,
            description_placeholders={"mode": self.draft.get(CONF_MODE, "")},
        )

    async def async_step_key(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if (
                user_input[CONF_KEY_MODE] == KEY_MODE_SAVED
                and not user_input.get(CONF_KEY_NAME)
            ):
                errors[CONF_KEY_NAME] = "key_name_required"
            else:
                self.draft.update(user_input)
                return await self.async_step_advanced()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_KEY_MODE,
                    default=self.draft.get(CONF_KEY_MODE, KEY_MODE_EPHEMERAL),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=KEY_MODES,
                        translation_key="key_mode",
                        mode=selector.SelectSelectorMode.LIST,
                    )
                ),
                vol.Optional(
                    CONF_KEY_NAME, default=self.draft.get(CONF_KEY_NAME, "")
                ): str,
            }
        )
        return self.async_show_form(
            step_id="key", data_schema=schema, errors=errors
        )

    async def async_step_advanced(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        if user_input is not None:
            self.draft.update(user_input)
            self.draft.setdefault(CONF_ENABLED, True)
            return await self._async_finish()

        schema = vol.Schema(
            {
                vol.Optional(
                    CONF_REGION, default=self.draft.get(CONF_REGION, DEFAULT_REGION)
                ): str,
                vol.Optional(
                    CONF_ALLOW_NODEKEY,
                    default=self.draft.get(CONF_ALLOW_NODEKEY, ""),
                ): str,
            }
        )
        return self.async_show_form(step_id="advanced", data_schema=schema)


class TailcatConfigFlow(_TailcatFlowMixin, ConfigFlow, domain=DOMAIN):
    """Handle creation of a new tailcat tunnel."""

    VERSION = 1

    def _step_defaults(self) -> dict[str, Any]:
        return {}

    async def _async_finish(self) -> FlowResult:
        return self.async_create_entry(
            title=self.draft[CONF_NAME], data={}, options=self.draft
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return TailcatOptionsFlow(config_entry)


class TailcatOptionsFlow(_TailcatFlowMixin, OptionsFlow):
    """Reconfigure an existing tailcat tunnel using the same wizard steps."""

    def __init__(self, config_entry: ConfigEntry) -> None:
        self.config_entry = config_entry

    def _step_defaults(self) -> dict[str, Any]:
        defaults = dict(self.config_entry.options)
        defaults[CONF_NAME] = self.config_entry.title
        return defaults

    async def _async_finish(self) -> FlowResult:
        # The entry title itself is renamed by the update listener in
        # __init__.py, which compares CONF_NAME against the current title.
        return self.async_create_entry(title="", data=self.draft)
