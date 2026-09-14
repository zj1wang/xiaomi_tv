"""Add support for the Xiaomi TVs."""
import logging
import time, datetime

from homeassistant.components import media_source
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
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
from .const import DOMAIN
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
    if host is not None:
        async_add_entities([XiaomiTV(entry.entry_id, host, name)], True)

class XiaomiTV(MediaPlayerEntity):
    """Represent the Xiaomi TV for Home Assistant."""

    def __init__(self, entry_id, ip, name):
        
        self._attr_unique_id = entry_id
    
        self.ip = ip
        self._attr_name = name
        self._attr_media_title = name
        self._volume_level = 1
        self._is_volume_muted = False
        # ⚠️ 初始值不能是 off。HA 的 HomeKit 用
        #   `state in (off, unknown, standby, "None")` 决定 Active 特征，
        # 报成 off 就会让 iOS 下一次按电源键发 Active=1 → turn_on，
        # 而 turn_on 按设计不发按键（见下面 async_turn_on 的说明），
        # 于是"每隔一次按电源键就没反应"。保持非 off 才能让每次按键都走
        # turn_off → 发 power。
        self._state = STATE_ON
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
        return True

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
    # iOS 遥控器/家庭 App 的电源键走的是 HomeKit 的 Active 特征，HA 会把它翻成
    # media_player.turn_on / turn_off（不会抛 homekit_tv_remote_key_pressed 事件）。
    #
    # ⚠️ 两个方向**不能**都发 power，虽然 power 是翻转键。
    # 原因：HomeKit 调 turn_on 有两种完全不同的场景，从实体侧区分不了 ——
    #   (a) 用户按电源键，真的想开机；
    #   (b) iOS 认为这台电视"关着"，于是你在按**任意**遥控器按键（哪怕是方向键）时，
    #       它先补一个 Active=1 把配件"唤醒" —— 而这时电视其实是开着的。
    # 场景 (b) 下发 power 就会把刚打开的电视关掉，
    # 表现就是「打开电视后第一次按遥控器，电视自己关机了」（2026-09-14 实测的 bug）。
    #
    # 而且这两种场景在协议层**没法区分**：判断不了真实开关机
    # （待机时 6095 端口照样在线，见 docs/mitv-6095-api.md 第五节）。
    # 所以只有"关"这个方向能发按键，"开"这个方向只能交给外部
    # （拿下面 fire_event('on') 抛的 xiaomi_tv 事件去接智能插座/小爱）。
    #
    # ⚠️ 由此推出第二条规则：**这个实体永远不能把状态报成 off**
    # （off / unknown / standby 都会让 Active 变 0）。因为一旦报成 off，
    # iOS 下一次按电源键发的是 Active=1 → turn_on，而 turn_on 按设计不发按键
    # → 症状是"每隔一次按电源键就没反应"。保持 Active 恒为 1，
    # 每次按电源键才会走 turn_off → 发 power → 电视翻转。
    # （原来靠每 30s 轮询把状态刷回 playing 掩盖了这个问题，轮询删掉后就暴露了。）
    async def async_turn_off(self):
        # 只发按键，**不动 _state**（理由见上面第二条规则）
        _LOGGER.warning('[调试] 收到电源键 -> turn_off，发送 keyevent power')
        await keyevent(self.ip, 'power')
        self.fire_event('off')

    async def async_turn_on(self):
        # 这里**故意不发 power**（理由见上面）。只把状态置成 on 并抛事件，
        # 状态置 on 还有个副作用是让 HomeKit 的 Active 立刻变 1，
        # iOS 就不会再重复发"唤醒"写入。
        self._state = STATE_ON
        _LOGGER.warning('[调试] 收到电源键 -> turn_on（按设计不发按键）')
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
            self._state = STATE_PLAYING
        else:
            await keyevent(self.ip, 'home')

    async def async_media_pause(self):
        result = await self.dlna.async_media_pause()
        if result:
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
    # 现在 _state 只由我们自己的动作维护，别的什么都不改它：
    #   __init__()                         -> STATE_ON（不能是 off，见电源键那段）
    #   async_turn_on()                    -> STATE_ON
    #   async_turn_off()                   -> 不改（必须保持非 off，见电源键那段）
    #   async_media_play() / _pause()      -> STATE_PLAYING / STATE_PAUSED
    # 电视真实的开关机状态不可知，这也是 assumed_state = True 的意思。
    async def async_update(self):
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