# 小米电视 6095 端口 HTTP API 参考

电视内置一个 HTTP 服务在 **6095** 端口，不需要认证，局域网内直接 GET 就能用。
本文的接口清单是**实测**得到的（对 `192.168.31.39` 逐项探测），不是抄文档。

## 一、controller?action=... 支持的接口

| action | 参数 | 作用 | 实测 |
|---|---|---|---|
| `getsysteminfo` | — | 设备名 / 设备ID / 平台号 / WiFi、有线 MAC | ✅ |
| `getvolume` | — | 当前音量与最大值 | ✅ |
| `getsources` | — | 信号源列表（sourceId + sourceName） | ✅ |
| `getinstalledapp` | `count=999`、`changeIcon=1` | 已安装应用列表（含图标 URL） | ✅ |
| `keyevent` | `keycode=` | 发送遥控按键 | ✅ |
| `startapp` | `type=packagename`、`packagename=` | 启动指定应用 | ✅ |
| `changesource` | `source=` | 切换信号源 | ✅（代码在用） |
| `capturescreen` | `compressrate=100` + `opaque` 签名 | 截屏 | ✅（代码在用） |

`request?action=...` 这一组也是一样的用法：

| action | 参数 | 作用 |
|---|---|---|
| `isalive` | — | 设备名 / IP / feature / platform / version |
| `getResource` | `name=com.xxx.0.png` | 取资源（应用图标、截屏图片） |

### 实测不存在的 action

`getapplist`、`getpowerstate`、`getsource`、`getcurrentapp`、`getstate`、`getdeviceinfo`、
`getdevicename`、`getdeviceid`、`getfeature`、`getversion`、`getplatform`、`getbuild`、
`getnetworkinfo`、`getwifiinfo`、`getethinfo`、`getmac`、`getipinfo`、`getbrightness`、
`getmute`、`getplaystatus`、`getscreenstate`、`getcurrentsource`、`getsourcelist`、
`setvolume`、`setsource`、`getsettings`、`getservices`、`getkeylist`、`getappinfo`、
`getlanguage`、`getfirmware`、`getmediainfo`、`getapp`

**注意没有"读取开关机状态"的接口**，原因见下面第五节。

## 二、怎么自己判断某个 action 存不存在

返回格式有规律，可以拿来做无副作用探测：

| 情况 | 响应 |
|---|---|
| 成功 | `{"status":0,"msg":"success","data":{...}}` |
| 参数缺失或非法 | `{"status":0,"msg":"error","data":null}` |
| **action 不存在** | **空响应体**（HTTP 200，body 为空） |

```bash
# 存在就是非空，不存在就是空
curl -s "http://<电视IP>:6095/controller?action=getvolume"
```

> 探测时避开有副作用的：`keyevent`（真的按键）、`startapp`（真的启动应用）、
> `changesource`（真的切信号源）。其余 `get*` / `isalive` 都是只读的，随便试。

## 三、keyevent 支持的 keycode（只有 11 个）

| keycode | 作用 |
|---|---|
| `power` | 开关机（**翻转**：开着就关，关着就开） |
| `up` | 光标上 |
| `down` | 光标下 |
| `left` | 光标左 |
| `right` | 光标右 |
| `enter` | 确认 |
| `home` | 返回桌面 |
| `back` | 返回 |
| `menu` | 打开菜单 |
| `volumeup` | 音量 +1 |
| `volumedown` | 音量 -1 |

```bash
curl "http://<电视IP>:6095/controller?action=keyevent&keycode=down"
```

这份清单来自三个互相独立的来源（pymitv、pymitv4 的 README、SumyBlog 的协议整理），
以及本项目 `custom_components/xiaomi_tv/utils.py` 里的 `ACTION_KEYS`，四者完全一致。

### 单独验证某个 keycode 是否被接受（不用瞎试）

**有效 keycode** 返回 `HTTP 200` + `msg:success` + `data:{}`；
**无效 keycode** 返回 `HTTP 404` + `msg:error` + `data:null`。

所以可以先用一个明显不存在的 keycode 确认 API 确实在校验这个参数（无副作用），
再发真的：

```bash
# 确认 API 会校验 keycode —— 期望 HTTP 404 / msg:error
curl -sS -o /dev/null -w "%{http_code}\n" \
  "http://<IP>:6095/controller?action=keyevent&keycode=zzz_not_a_key"

# 再发真按键 —— 期望 HTTP 200 / msg:success
curl "http://<IP>:6095/controller?action=keyevent&keycode=power"
```

> ⚠️ `msg:success` 只证明 **API 收下了这个键**，不证明电视真的执行了
> （协议层面待机时请求照样 success）。「按键有没有真的生效」只能靠眼睛看，
> 或者用下面的实测记录做参考。

### 实测记录

| 日期 | keycode | 结果 |
|---|---|---|
| 2026-09-13 | `power` | ✅ API 200/success，**且电视真的关机了** |
| 2026-09-13 | `home` | ✅ 经 iOS 遥控器的播放-暂停键实测生效（电视回主页） |
| 2026-09-13 | `zzz_not_a_key` | ❌ 404/error（作为对照） |

> `utils.py` 里出现的 `'enter-2'` **不是 keycode**，是本项目自己的延时语法
> （`按键-等待秒数`），实际发出去的还是 `enter`。

## 四、你这台电视的实际信息（实测）

```
devicename : 客厅电视
platform   : 1235        build : -1        version : 16777510
wifimac    : 4c:24:ce:33:02:3f
ethmac     : 3c:2c:a6:ff:53:7a
音量       : 11 / 100    (stream: music)
```

**信号源只有 6 个**：

| sourceId | sourceName |
|---|---|
| 23 | HDMI1 |
| 24 | HDMI2 |
| 25 | HDMI3 |
| 28 | DTMB |
| 2 | AV |
| 1 | TV |

> ⚠️ **没有 VGA**。但集成里的 `_sound_mode_list` 硬编码了
> `['hdmi1','hdmi2','hdmi3','gallery','aux','tv','vga','av','dtmb','adb']`，
> 在 HA 里选 VGA 会去调 `changesource&source=vga`，电视会返回 error。

**已安装的 20 个应用**（可用 `startapp` 启动，或在 HA 里用 `media_player.select_source` 选名字）：

| 应用 | 包名 |
|---|---|
| VidHub | `com.oumi.utility.media.hub` |
| 云视听小电视 | `com.xiaodianshi.tv.yst` |
| 桌面 | `com.mitv.tvhome` |
| 相册 | `com.mitv.gallery` |
| 咪视界 | `cn.miguvideo.migutv` |
| TVBox | `com.github.tvbox.osc.tk` |
| 网易爆米花 | `com.netease.filmlytv.xiaomitv` |
| 电视直播 | `com.github.mytv.android` |
| 央视频TV | `com.newtv.cboxtv` |
| 银河奇异果 | `com.gitvdemo.video` |
| 云视听极光 | `com.ktcp.video` |
| 网易云音乐 | `com.netease.cloudmusic.tv` |
| 电视设置 | `com.xiaomi.mitv.settings` |
| 当贝市场 | `com.dangbeimarket` |
| 电视管家 | `com.xiaomi.mitv.tvmanager` |
| 飞牛TV | `com.trim.tv` |
| Kodi | `org.xbmc.kodi` |
| 无线投屏 | `com.xiaomi.mitv.smartshare` |
| CIBN酷喵 | `com.cibn.tv` |
| 小爱同学 | `com.xiaomi.voicecontrol` |

## 五、重要限制：这个协议无法判断真实开关机状态

pymitv 的文档里有一句原话：

> **If the TV is in standby mode, this request will still return as if it were on.
> Currently there is no way to check if the TV is actually on.**

也就是说：**待机（假关机，屏幕灭了但系统还在跑）时，6095 端口照样在线、照样返回 success。**
这是协议层面的限制，不是某个集成的 bug——任何基于 6095 的实现都躲不过。

所以「电视到底开没开」必须从别的来源拿：计量插座的功率、ADB 查屏幕状态、或者干脆不判断。

## 六、附：常用调用

```bash
# 发送按键
curl "http://<IP>:6095/controller?action=keyevent&keycode=enter"

# 启动应用（以 TVBox 为例）
curl "http://<IP>:6095/controller?action=startapp&type=packagename&packagename=com.github.tvbox.osc.tk"

# 切信号源（以 HDMI2 为例）
curl "http://<IP>:6095/controller?action=changesource&source=hdmi2"

# 获取应用列表
curl "http://<IP>:6095/controller?action=getinstalledapp&count=999&changeIcon=1"
```
