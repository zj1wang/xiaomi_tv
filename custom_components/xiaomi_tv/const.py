DOMAIN = "xiaomi_tv"
SERVICE_ADB_COMMAND = "adb_command"
SEND_KEY = "send_key"
PLATFORMS = ["media_player"]

# 用来判断电视开关机状态的外部实体（不选则由集成自己维护状态）。
# 可以是 switch / input_boolean / binary_sensor 等。典型用法：
#   把 xiaomihome 的「是否为音箱模式」实体选进来，用它判断开关机。
CONF_POWER_ENTITY = "power_entity"

# 不想走 UI 选项的话，直接把实体 id 写在这里也行，例如 "binary_sensor.tv_speaker_mode"。
# 填了就以这里为准（优先级最高）；留空才用集成选项里选的那个。
DEFAULT_POWER_ENTITY = ""

# xiaomihome（米家）电视的 media_player 实体。选了之后，遥控按键走 xiaomihome
# 暴露的 button 实体（自动发现同 device 的 button），否则退回 6095 keyevent 直连。
CONF_TV_ENTITY = "tv_entity"
DEFAULT_TV_ENTITY = ""

# 这个 switch 是反着接的：开关为 on = 电视关机，开关为 off = 电视开机。
# 如果你的开关是正逻辑（on = 开机），把这个改成 False。
POWER_ENTITY_INVERTED = True