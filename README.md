# 小米电视

视频介绍：https://www.bilibili.com/read/cv12067446

[![hacs_badge](https://img.shields.io/badge/Home-Assistant-%23049cdb)](https://www.home-assistant.io/)
[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
![visit](https://visitor-badge.laobi.icu/badge?page_id=shaonianzhentan.xiaomi_tv&left_text=visit)

[![badge](https://img.shields.io/badge/Conversation-语音小助手-049cdb?logo=homeassistant&style=for-the-badge)](https://github.com/shaonianzhentan/conversation)

## 使用方式

安装完成重启HA，刷新一下页面，在集成里搜索`小米电视`即可

[![Add Integration](https://my.home-assistant.io/badges/config_flow_start.svg)](https://my.home-assistant.io/redirect/config_flow_start?domain=xiaomi_tv)

HomeKit遥控器

[![导入蓝图](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fshaonianzhentan%2Fxiaomi_tv%2Fblob%2Fmain%2Fblueprints%2Fhomekit_tv_remote.yaml)

开机/关闭电视事件

[![导入蓝图](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fshaonianzhentan%2Fxiaomi_tv%2Fblob%2Fmain%2Fblueprints%2Fxiaomi_tv.yaml)


> 遥控器按键命令
- 关机：`power`
- 上：`up`
- 下：`down`
- 左：`left`
- 右: `right`
- 首页：`home`
- 音量加：`volumeup`
- 音量减：`volumedown`
- 菜单：`menu`
- 确定：`enter`
- 返回：`back`

发送按键
```yaml
service: xiaomi_tv.send_key
data:
  key: left
```

### iOS 遥控器（HomeKit）的按键映射

遥控器上不同类型的按键，在 Home Assistant 里走的是完全不同的链路：

| 遥控器按键 | HomeKit 特征 | 实际动作 |
|---|---|---|
| 方向 / 确认 / 返回 / 信息 | `RemoteKey` → 抛 `homekit_tv_remote_key_pressed` 事件 | 「iOS电视遥控」蓝图 → `xiaomi_tv.send_key` |
| 播放-暂停 | 被 HA 拦成 `media_player.media_pause` / `media_play` | 发 `keyevent&keycode=home`（电视回主页） |
| 电源 | `Active` → `media_player.turn_off`（**只有这个方向**） | 发 `keyevent&keycode=power` |

> 播放-暂停和电源键**都不会抛 `homekit_tv_remote_key_pressed` 事件**，
> 所以在蓝图里配不出来，只能由集成内部处理。
> 原因是 `TelevisionMediaPlayer.set_remote_key()` 里对
> `play_pause` 做了特判（只要实体声明了 `PLAY|PAUSE` 就直接调服务并 `return`），
> 而电源键压根不走 `RemoteKey` 特征。

> ⚠️ **开机的方向故意不发按键**：`media_player.turn_on` 除了"用户想开机"，
> 还会被 iOS 用来在按任意遥控器按键前"唤醒"它以为关着的配件 ——
> 这时电视其实是开着的，发 `power`（翻转键）反而会把它关掉。
> 两种场景在协议层区分不了（待机时 6095 照样在线），所以 `async_turn_on()`
> 只抛 `xiaomi_tv` 的 `on` 事件，真正开机请用那个事件外接（智能插座 / 小爱）。

## ADB服务

打开ADB（注意：必须先打开`开发者模式`）
```yaml
service: xiaomi_tv.send_key
data:
  key: adb
  entity_id: media_player.xiao_mi_dian_shi
```
腾讯视频搜索
```yaml
service: xiaomi_tv.adb_command
data:
  command: am start -a com.tencent.qqlivetv.open -d "tenvideo2://?action=9&search_key=扫黑风暴"
  entity_id: media_player.xiao_mi_dian_shi
```
腾讯视频播放
```yaml
service: xiaomi_tv.adb_command
data:
  command: am start -a com.tencent.qqlivetv.open -d "tenvideo2://?action=7&cover_id=mzc00200lxzhhqz"
  entity_id: media_player.xiao_mi_dian_shi
```
酷喵搜索
```yaml
service: xiaomi_tv.adb_command
data:
  command: am start -a android.intent.action.VIEW -d "ykott://tv/search?url=tv/v3/search?from_app=cn.cibntv.ott"
  entity_id: media_player.xiao_mi_dian_shi
```
酷喵视频播放
```yaml
service: xiaomi_tv.adb_command
data:
  command: am start -a android.intent.action.VIEW -d "ykott://tv/detail?url=tv/v3/show/detail?id=175957&fullscreen=true&fullback=true&from=cn.cibntv.ott"
  entity_id: media_player.xiao_mi_dian_shi
```

## 如果这个项目对你有帮助，请我喝杯<del style="font-size: 14px;">咖啡</del>奶茶吧😘
|支付宝|微信|
|---|---|
<img src="https://ha.jiluxinqing.com/img/alipay.png" align="left" height="160" width="160" alt="支付宝" title="支付宝">  |  <img src="https://ha.jiluxinqing.com/img/wechat.png" align="left" height="160" width="160" alt="微信支付" title="微信">

#### 关注我的微信订阅号，了解更多HomeAssistant相关知识
<img src="https://ha.jiluxinqing.com/img/wechat-channel.png" height="160" alt="HomeAssistant家庭助理" title="HomeAssistant家庭助理"> 

---
**在使用的过程之中，如果遇到无法解决的问题，付费咨询请加Q`635147515`**