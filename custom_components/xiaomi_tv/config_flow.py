from __future__ import annotations

from typing import Any
import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, OptionsFlow, ConfigEntry
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import DOMAIN, CONF_TURN_ON_ENTITY
from homeassistant.components import zeroconf
from .discovery import AsyncXiaomiTVScanner

# 「开机开关实体」可以选择的域名，这些域都有 turn_on 服务
TURN_ON_DOMAINS = ["switch", "input_boolean", "light", "fan", "script"]

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
            if name != '' and ip != '':
                return self.async_create_entry(title=name, data={
                    'name': name,
                    'ip': ip,
                    # 开机时打开的开关实体，留空则用局域网 power 按键开机
                    CONF_TURN_ON_ENTITY: user_input.get(CONF_TURN_ON_ENTITY) or ''
                })
        
        hosts = await self.discovery()
        ip = options.get('ip', '')
        # 开机开关实体：点电源键开机时才会被打开；关机始终走电视自身的关机逻辑
        turn_on_entities = { '': '（不使用）直接发送局域网 power 按键开机' }
        for entity_id in self.hass.states.async_entity_ids():
            if entity_id.split('.')[0] in TURN_ON_DOMAINS:
                state = self.hass.states.get(entity_id)
                turn_on_entities[entity_id] = f"{state.name}（{entity_id}）" if state else entity_id
        # 之前保存的实体可能已经不存在了，补回列表里避免下拉框选中失败
        saved_entity = options.get(CONF_TURN_ON_ENTITY)
        if saved_entity and saved_entity not in turn_on_entities:
            turn_on_entities[saved_entity] = saved_entity
        turn_on_entity = vol.Optional(CONF_TURN_ON_ENTITY, default=saved_entity or '')

        if hosts is None:
            DATA_SCHEMA = vol.Schema({
                vol.Required("name", default=options.get('name', '小米电视')): str,
                vol.Required("ip", default=ip): str,
                turn_on_entity: vol.In(turn_on_entities)
            })
        else:
            DATA_SCHEMA = vol.Schema({
                vol.Required("ip", default=ip): vol.In(hosts),
                turn_on_entity: vol.In(turn_on_entities)
            })
        return self.async_show_form(step_id="user", data_schema=DATA_SCHEMA, errors=errors)
