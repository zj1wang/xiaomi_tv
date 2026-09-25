from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, OptionsFlow, ConfigEntry
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, CONF_POWER_ENTITY, CONF_TV_ENTITY
from homeassistant.components import zeroconf
from .discovery import AsyncXiaomiTVScanner

# 下拉里表示「不使用」的值（空串，不要改成 None）
NO_POWER_ENTITY = ""
NO_TV_ENTITY = ""

# 可作为「开关机状态源」的实体域（xiaomihome 的音箱模式可能是 switch 或 binary_sensor）
_POWER_DOMAINS = ("switch", "binary_sensor", "input_boolean")

class XiaomiConfigFlow(ConfigFlow, domain=DOMAIN):

    VERSION = 1
    devices = []

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> FlowResult:
        errors = {}
        if user_input is None:
            DATA_SCHEMA = vol.Schema({})
            return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA, errors=errors)
        return self.async_create_entry(title=DOMAIN, data=user_input)

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry):
        return OptionsFlowHandler(entry)


class OptionsFlowHandler(OptionsFlow):
    def __init__(self, config_entry: ConfigEntry) -> None:
        super().__init__()
        # In Core 2026.5.4, self.config_entry is automatically set up 
        # as a read-only property behind the scenes by the framework.
        self.hosts = None

    async def async_step_init(self, user_input=None):
        return await self.async_step_user(user_input)

    async def discovery(self):
        zc = await zeroconf.async_get_instance(self.hass)
        devices = await AsyncXiaomiTVScanner(zc)
        if len(devices) > 0:
            hosts = {}
            for item in devices:
                ip = item['ip']
                name = item['name'].split('.')[0]
                hosts[ip] = f"{name}（{ip}）"
            self.hosts = hosts
            return hosts
        return None

    def power_entities(self):
        ''' 可选的状态开关：所有 switch 实体，第一项是「不启用」 '''
        # 用 vol.In(dict) 做下拉，不用 selector.EntitySelector：
        # 后者对空值会抛 vol.Invalid，导致表单存不下去。
        entities = { NO_POWER_ENTITY: "不启用（由集成自己维护状态）" }
        for entity_id in sorted(self.hass.states.async_entity_ids("switch")):
            state = self.hass.states.get(entity_id)
            friendly_name = state.attributes.get("friendly_name") if state else None
            entities[entity_id] = f"{friendly_name}（{entity_id}）" if friendly_name else entity_id
        # 已选中的实体即使当前不存在也要留在列表里，否则表单打不开
        current = self.config_entry.options.get(CONF_POWER_ENTITY, NO_POWER_ENTITY)
        if current and current not in entities:
            entities[current] = current
        return entities

    async def async_step_user(self, user_input=None):
        hosts = self.hosts
        options = self.config_entry.options 
        errors = {}
        if user_input is not None:
            ip = user_input['ip']
            print(ip)
            if hosts is None:
                name = user_input['name']
            else:
                name = hosts[ip].split('（')[0]
            power_entity = user_input.get(CONF_POWER_ENTITY, NO_POWER_ENTITY)
            if name != '' and ip != '':
                return self.async_create_entry(title=name, data={
                    'name': name,
                    'ip': ip,
                    CONF_POWER_ENTITY: power_entity
                })
        
        hosts = await self.discovery()
        ip = options.get('ip', '')
        power_entity = options.get(CONF_POWER_ENTITY, NO_POWER_ENTITY)
        if hosts is None:
            DATA_SCHEMA = vol.Schema({
                vol.Required("name", default=options.get('name', '小米电视')): str,
                vol.Required("ip", default=ip): str,
                vol.Required(CONF_POWER_ENTITY, default=power_entity): vol.In(self.power_entities())
            })
        else:
            DATA_SCHEMA = vol.Schema({
                vol.Required("ip", default=ip): vol.In(hosts),
                vol.Required(CONF_POWER_ENTITY, default=power_entity): vol.In(self.power_entities())
            })
        return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA, errors=errors)
