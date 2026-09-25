"""Add support for the Xiaomi TVs."""
import logging
import time, datetime

from homeassistant.components import media_source
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.storage import STORAGE_DIR
from homeassistant.components.media_player import (
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaType,
    BrowseMedia, 
    async_process_play_media_url
)
from homeassistant.const import (
    CONF_HOST, 
    CONF_NAME,
    STATE_OFF, 
    STATE_ON, 
    STATE_PLAYING, 
    STATE_PAUSED,
    STATE_UNAVAILABLE
)

from .manifest import manifest
from .const import DOMAIN, CONF_POWER_ENTITY, DEFAULT_POWER_ENTITY, POWER_ENTITY_INVERTED
from .utils import keyevent, startapp, getsysteminfo, changesource, getinstalledapp, capturescreen, open_app
from .dlna import MediaDLNA
from .adb import MediaADB

_LOGGER = logging.getLogger(__name__)

SUPPORT_XIAOMI_TV = (
  MediaPlayerEntityFeature.VOLUME_STEP 
  | MediaPlayerEntityFeature.VOLUME_MUTE 
  | MediaPlayerEntityFeature.VOLUME_SET 
  | MediaPlayerEntityFeature.TURN_ON 
  | MediaPlayerEntityFeature.TURN_OFF 
  | MediaPlayerEntityFeature.SELECT_SOURCE 
  | MediaPlayerEntityFeature.SELECT_SOUND_MODE 
  | MediaPlayerEntityFeature.PLAY_MEDIA 
  | MediaPlayerEntityFeature.PLAY 
  | MediaPlayerEntityFeature.PAUSE 
  | MediaPlayerEntityFeature.PREVIOUS_TRACK 
  | MediaPlayerEntityFeature.NEXT_TRACK 
  | MediaPlayerEntityFeature.BROWSE_MEDIA
)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    config = entry.options
    host = config.get('ip')
    name = config.get(CONF_NAME)
    # 外部状态开关：选了之后，开关机状态只由它决定
    # const.py 里写死的 DEFAULT_POWER_ENTITY 优先级最高，其次才是选项里选的
    power_entity = DEFAULT_POWER_ENTITY or config.get(CONF_POWER_ENTITY)
    if host is not None:
        async_add_entities([XiaomiTV(entry.entry_id, host, name, power_entity)], True)

class XiaomiTV(MediaPlayerEntity):
    """Represent the Xiaomi TV for Home Assistant."""

    def __init__(self, entry_id, ip, name, power_entity=None):
        
        self._attr_unique_id = entry_id
    
        self.ip = ip
        # 判断开关机用的外部 switch 实体（None/空 = 没配，状态由集成自己维护）
        self._power_entity = power_entity or None
        self._attr_name = name
        self._attr_media_title = name
        self._volume_level = 1
        self._is_volume_muted = False
        self._state = STATE_OFF
        self._source_list = []
        self._sound_mode_list = ['hdmi1', 'hdmi2', 'hdmi3', 'gallery', 'aux', 'tv', 'vga', 'av', 'dtmb', 'adb']
        # DLNA媒体设备
        self.dlna = MediaDLNA(ip)
        self.adb = MediaADB(ip, self)
        # 更新时间
        self.update_at = None
        # 已知应用列表
        self.app_list = []
        self.apps = {
                # '云视听极光': 'com.ktcp.video',
                # '芒果TV': 'com.hunantv.license',
                # '银河奇异果': 'com.gitvdemo.video',
                # 'CIBN酷喵': 'com.cibn.tv',
                # '视频头条': 'com.duokan.videodaily',
                # '小米通话': 'com.xiaomi.mitv.tvvideocall',
                # 'QQ音乐': 'com.tencent.qqmusictv',
                # '定时提醒': 'com.mitv.alarmcenter',
                # '天气': 'com.xiaomi.tweather',
                # '用户手册': 'com.xiaomi.mitv.handbook',
                # '桌面': 'com.mitv.tvhome',
                # '电视管家': 'com.xiaomi.mitv.tvmanager',
                # '日历': 'com.xiaomi.mitv.calendar',
                # '小爱同学': 'com.xiaomi.voicecontrol',
                # '相册': 'com.mitv.gallery',
                # '电视设置': 'com.xiaomi.mitv.settings',
                # '时尚画报': 'com.xiaomi.tv.gallery',
                # '无线投屏': 'com.xiaomi.mitv.smartshare'
            }
        # mitv ethernet Mac address
        self._attr_extra_state_attributes = {
            'platform': 'xiaomi',
            'ip': self.ip
        }

    @property
    def volume_level(self):
        return self._volume_level

    @property
    def is_volume_muted(self):
        return self._is_volume_muted

    @property
    def state(self):
        """Return _state variable, containing the appropriate constant."""
        return self._state

    @property
    def assumed_state(self):
        """Indicate that state is assumed."""
        # 配了外部开关后状态是实测值，不再是猜的
        return self._power_entity is None

    # ── 开关机状态：只认外部开关 ────────────────────────────────────────────
    # 协议层判断不了真实的开关机（电视待机时 6095 端口照样在线、请求照样 success，
    # 见 docs/mitv-6095-api.md 第五节），所以如果有人在集成选项里选了一个 switch，
    # 开关机状态就完全由那个 switch 决定，其它任何来源都不改状态。
    #
    # ⚠️ 这个 switch 是**反着接**的（POWER_ENTITY_INVERTED = True）：
    #     switch 为 on  -> 电视关机
    #     switch 为 off -> 电视开机
    # （常见于「检测到电流/信号才置位」的那类开关，这里按反逻辑映射。）
    def _sync_power_state(self):
        if self._power_entity is None:
            return
        state = self.hass.states.get(self._power_entity)
        # 开关自身 unavailable / unknown 时不改状态，沿用上一次的已知值
        if state is None or state.state in (STATE_UNAVAILABLE, 'unknown'):
            return
        switch_on = state.state == STATE_ON
        # 反逻辑：开关开着说明电视关着；正逻辑则一致
        self._state = STATE_OFF if (switch_on == POWER_ENTITY_INVERTED) else STATE_ON

    @callback
    def _async_power_entity_changed(self, event):
        ''' 外部开关变了就立刻刷新状态 '''
        self._sync_power_state()
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        if self._power_entity is not None:
            self._sync_power_state()
            self.async_on_remove(async_track_state_change_event(
                self.hass, [self._power_entity], self._async_power_entity_changed
            ))

    @property
    def sound_mode_list(self):
        return self._sound_mode_list

    @property
    def source_list(self):
        return self._source_list

    @property
    def media_duration(self):
        return self.dlna.media_duration

    @property
    def media_position(self):
        return self.dlna.media_position

    @property
    def supported_features(self):
        """Flag media player features that are supported."""
        return SUPPORT_XIAOMI_TV

    @property
    def device_class(self):
        return 'tv'

    @property
    def device_info(self):
        return {
            "identifiers": {
                (DOMAIN, self._attr_unique_id)
            },
            "name": self._attr_name,
            "manufacturer": "Xiaomi",
            "model": self.ip,
            "sw_version": manifest.version
        }

    async def async_browse_media(
        self,
        media_content_type: MediaType | str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        """Implement the websocket media browsing helper."""
        return await media_source.async_browse_media(
            self.hass,
            media_content_id,
            content_filter=None,
        )

    # 选择应用
    async def async_select_source(self, source):
        app = self.apps[source]
        if app is not None:
            # 判断是否视频源
            if self.sound_mode_list.count(app) > 0:
                await self.async_select_sound_mode(app)
                return

            # 在选择应用时，先回到首页
            await open_app(self.hass, self.ip, app)

    # 选择数据源
    async def async_select_sound_mode(self, sound_mode):
        if self.sound_mode_list.count(sound_mode) > 0:
            self.fire_event(sound_mode)
            if sound_mode == 'adb':
                await self.hass.services.async_call('xiaomi_tv', 'send_key', {
                    'entity_id': self.entity_id,
                    'key': 'adb'
                })
            else:
                await changesource(self.ip, sound_mode)

    # ── 电源键 ──────────────────────────────────────────────────────────────
    # iOS 遥控器/家庭 App 的电源键走的是 HomeKit 的 Active 特征，HA 把它翻成
    # media_player.turn_on / turn_off（type_media_players.py::TelevisionMediaPlayer
    # 的 set_on_off：写 1 -> turn_on，写 0 -> turn_off，**不做去重**）。
    #
    # 这个 switch 既是「状态源」也是「执行器」：把开关打到某一侧，电视就真的开/关了。
    # 所以配了开关后，开关机只操作这个开关，**不再发 power 按键**
    # （开关本身已经把电源动作做了，再发一次 power 等于翻转两次 = 没反应）：
    #       关机 -> switch.turn_on  （开关为 on  = 电视关机）
    #       开机 -> switch.turn_off （开关为 off = 电视开机）
    #
    # ⚠️⚠️ turn_on **绝对不能**做成「翻转」：
    # iOS 在**打开遥控器界面**时就会补写一次 Active=1（它认为配件该被唤醒），
    # 跟你按的是电源键还是方向键无关。2026-09-25 实测：HomeKit 开机后按一下方向键，
    # 这次补写照样进 turn_on —— 做成翻转就会把刚打开的电视关掉。
    # 所以 turn_on 只能是「确保开机」（幂等），关电视只能靠 turn_off。
    #
    # 没配开关时才退回老路子：turn_off 发 power；turn_on **故意不发按键** ——
    # 那种情况下状态是猜的，同样的补写会把开着的电视关掉（2026-09-14 实测的 bug）。
    async def _async_call_switch(self, service):
        _LOGGER.warning(f'[调试] 收到电源键 -> switch.{service} {self._power_entity}')
        await self.hass.services.async_call('switch', service, {
            'entity_id': self._power_entity
        }, blocking=True)

    async def _async_set_power(self, tv_on):
        ''' 直接把开关打到某一侧：tv_on=True 表示要开机 '''
        if POWER_ENTITY_INVERTED:
            service = 'turn_off' if tv_on else 'turn_on'
        else:
            service = 'turn_on' if tv_on else 'turn_off'
        await self._async_call_switch(service)

    async def async_turn_off(self):
        self._state = STATE_OFF
        if self._power_entity is None:
            _LOGGER.warning('[调试] 收到电源键 -> turn_off，发送 keyevent power')
            await keyevent(self.ip, 'power')
        else:
            # 打开开关 = 电视关机，不用再做别的（开关已经是关着时也不会误翻转）
            await self._async_set_power(False)
        self.fire_event('off')

    async def async_turn_on(self):
        self._state = STATE_ON
        if self._power_entity is None:
            _LOGGER.warning('[调试] 收到电源键 -> turn_on（未配状态开关，按设计不发按键）')
        else:
            # 关闭开关 = 电视开机。电视已经开着时这次调用什么都不会做
            # （iOS 打开遥控器时的补写走的就是这里，绝不能翻转，见上面注释）。
            await self._async_set_power(True)
        self.fire_event('on')

    # 发送事件
    def fire_event(self, cmd):
        self.hass.bus.async_fire("xiaomi_tv", { 'entity_id': self.entity_id, 'type': cmd })

    async def async_volume_up(self):
        await keyevent(self.ip, 'volumeup')

    async def async_volume_down(self):
        await keyevent(self.ip, 'volumedown')

    async def async_mute_volume(self, mute):
        if mute:
            await self.async_set_volume_level(0)
        else:
            await self.async_set_volume_level(0.5)
        self._is_volume_muted = mute

    async def async_set_volume_level(self, volume):
        self._volume_level = volume
        # 小米盒子音量最大值15，当音量小于15时，则实际值设置
        if '盒子' in self._attr_media_title:
            if volume <= 0.15:
                arr = [0, 0.05, 0.1, 0.2, 0.25, 0.3, 0.4, 0.45, 0.5, 0.6, 0.65, 0.7, 0.75, 0.85, 0.9, 1]
                volume = arr[int(volume * 100)]
        # 小米电视音量最大值50，当音量小于20时，则实际值设置
        elif '电视' in self._attr_media_title:
            if volume <= 0.2:
                volume = round(volume * 2.0, 2)
        # 调整音量
        await self.dlna.async_set_volume_level(volume)

    async def async_play_media(self, media_type, media_id, **kwargs):
        if media_source.is_media_source_id(media_id):
            media_type = MediaType.MUSIC
            play_item = await media_source.async_resolve_media(
                self.hass, media_id, self.entity_id
            )
            media_id = async_process_play_media_url(self.hass, play_item.url)

        if media_id.startswith('http'):
            self._attr_media_content_id = media_id
            await self.dlna.async_play_media(media_type, media_id)

    # ── iOS 遥控器的「播放/暂停」键 = 电视的「主页」键 ──────────────────────
    # HomeKit 不会把这些按键抛成 homekit_tv_remote_key_pressed 事件：
    # TelevisionMediaPlayer.set_remote_key() 里，只要实体声明了 PLAY|PAUSE
    # （本集成声明了），play_pause 就会被直接翻译成 media_player 服务调用：
    #     状态 playing  -> media_player.media_pause -> async_media_pause()
    #     状态 paused   -> media_player.media_play  -> async_media_play()
    #     其它状态      -> media_player.media_play_pause -> async_media_play_pause()
    #     且之后直接 return，永远不抛事件。
    # 所以蓝图里的 play_pause 映射是死代码，真正生效的是下面这三处兜底。
    async def async_media_play(self):
        result = await self.dlna.async_media_play()
        if result:
            # 配了外部开关时开关机状态只认开关，这里不能改
            if self._power_entity is None:
                self._state = STATE_PLAYING
        else:
            await keyevent(self.ip, 'home')

    async def async_media_pause(self):
        result = await self.dlna.async_media_pause()
        if result:
            if self._power_entity is None:
                self._state = STATE_PAUSED
        else:
            await keyevent(self.ip, 'home')

    async def async_media_play_pause(self):
        await keyevent(self.ip, 'home')

    async def async_media_next_track(self):
        await keyevent(self.ip, 'right')

    async def async_media_previous_track(self):
        await keyevent(self.ip, 'left')

    # 轮询只用来刷新「数据」：应用列表、扩展服务（DLNA/ADB）、截图。
    #
    # ⚠️ 这里**不再推断开关状态**（原来靠 check_port(6095) 判断在线，再把 _state
    # 推成 playing / off）。原因：协议层根本判断不了真实开关机 —— 电视待机时
    # 6095 端口照样在线、请求照样 success（见 docs/mitv-6095-api.md 第五节）。
    # 猜错的后果不只是显示不对：HomeKit 的 Active 会跟着错，
    # 进而触发 iOS「第一次操作遥控器时补发 Active=1」的行为。
    #
    # 开关机状态的两个来源，按优先级：
    #   1. 配了外部 switch（集成选项里选的）-> 只认它，通常靠状态变化事件即时刷新，
    #      这里的同步只是兜底；
    #   2. 没配 switch -> _state 只由我们自己的动作维护：
    #        async_turn_on()  -> STATE_ON
    #        async_turn_off() -> STATE_OFF
    #        async_media_play() / _pause() -> STATE_PLAYING / STATE_PAUSED
    #      电视真实的开关机状态不可知，这也是 assumed_state = True 的意思。
    async def async_update(self):
        # 开关机状态：只从外部开关同步（没配则什么都不做）
        self._sync_power_state()
        # 根据应用列表数量，判断是否初次更新
        if len(self.app_list) == 0:
            # 获取应用列表
            app_info = await getinstalledapp(self.ip)
            if app_info is not None:
                for app in app_info:
                    self.apps.update({ app['AppName']: app['PackageName'] })

            # 绑定视频源
            for mode in self._sound_mode_list:
                self.apps.update({ mode.upper(): mode })

            # 绑定数据源
            _source_list = []
            for name in self.apps:
                _source_list.append(name)
            self.app_list = self._source_list = _source_list
        # 调整扩展服务更新时间
        if self.update_at is None or (datetime.datetime.now() - self.update_at).seconds > 20:
            self.update_at = datetime.datetime.now()
            await self.dlna.async_update()
            await self.adb.async_update()
        # 获取截图（电视不可达时拿不到，保留上一次的图，不清空 —— 避免网络抖动导致缩略图闪）
        res = await capturescreen(self.ip)
        if res is not None:
            self._attr_media_image_url = res['url']
            self._attr_app_id = res['id']
            self._attr_app_name = res['name']