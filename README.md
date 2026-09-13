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

## iOS 遥控器（控制中心里的遥控器）的电源键

先说结论：**电源键不会触发 `homekit_tv_remote_key_pressed` 事件**，所以在 `homekit_tv_remote.yaml` 蓝图里是配不出电源键的。

HomeKit 协议里，遥控器的方向键/确认/返回走的是 `RemoteKey` 特征（HA 才抛出 `homekit_tv_remote_key_pressed` 事件），
而电源键走的是 `Active` 特征，Home Assistant 的 HomeKit 桥会把它翻译成：

| iOS 遥控器操作 | HomeKit | Home Assistant |
|---|---|---|
| 点电源键开机 | `Active = 1` | `media_player.turn_on` → `async_turn_on()` |
| 点电源键关机 | `Active = 0` | `media_player.turn_off` → `async_turn_off()` |

所以电源键能不能用，取决于集成里的 `async_turn_on()` / `async_turn_off()` 做了什么：

- **关机**：始终走电视自身的关机逻辑——发送局域网 `power` 按键（电视开机状态下 6095 端口在线）。
- **开机**：电视关机后 6095 端口通常已经掉线，局域网发不出按键，所以按下面的优先级处理。

### 开机方式（按优先级）

1. **配置了「开机开关实体」**——点电源键开机时，改为调用 `homeassistant.turn_on` 打开这个实体。

   在「设置 → 设备与服务 → 小米电视 → 配置」里选择，可选 `switch` / `input_boolean` / `light` / `fan` / `script`。
   典型用法：

   - 电视接了**智能插座**，通电即开机 → 选那个插座；
   - 开机需要多步动作（开插座 + 让小爱说话）→ 写个 **script**，这里选这个 script；
   - 想让 HomeKit 的开关和别的设备联动 → 用 **input_boolean** 当虚拟开关。

   ```yaml
   # 对应配置项：turn_on_entity
   # 里面存的就是一个实体 id，例如
   turn_on_entity: switch.dian_shi_cha_zuo
   ```

2. **没配置开关实体** → 用局域网 `power` 按键唤醒（电视待机时 6095 端口仍在线即可唤醒）。

3. **兜底**：把 `media_player.py` 顶部的 `TURN_ON_BY_KEY` 改成 `False`，
   改为抛出 `xiaomi_tv` 的 `on` 事件，由「小米电视」蓝图接管，例如：

   ```yaml
   # 「打开电视」的动作示例：让小爱音箱去开机
   service: xiaomi_miot.intelligent_speaker
   data:
     entity_id: media_player.xiao_ai_tong_xue
     text: 打开电视
     execute: true
   ```

> 三种方式是**互斥**的，只会执行命中的那一个，不会重复触发。关机不受影响，永远走电视自身逻辑。

另外两点：

- 实体必须是以 **TV accessory** 身份暴露给 HomeKit（集成里已经设置了 `device_class: tv`），
  iOS 控制中心的遥控器里才会出现这台电视；用 `homekit:` 的 `mode: accessory` 单独暴露最稳。
- 这个集成的开关状态是靠轮询 6095 端口推断的（`assumed_state`），电视待机但端口还在时会显示成"播放中"，
  此时点电源键 HomeKit 发的是 `turn_off`，属于已知的状态不同步问题。


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
  command: left
```

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