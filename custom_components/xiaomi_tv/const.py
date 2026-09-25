DOMAIN = "xiaomi_tv"
SERVICE_ADB_COMMAND = "adb_command"
SEND_KEY = "send_key"
PLATFORMS = ["media_player"]

# 用来判断电视开关机状态的外部 switch 实体（不选则由集成自己维护状态）
CONF_POWER_ENTITY = "power_entity"

# 不想走 UI 选项的话，直接把 switch 实体 id 写在这里也行，例如 "switch.tv_power"。
# 填了就以这里为准（优先级最高）；留空才用集成选项里选的那个。
DEFAULT_POWER_ENTITY = ""

# 这个 switch 是反着接的：开关为 on = 电视关机，开关为 off = 电视开机。
# 如果你的开关是正逻辑（on = 开机），把这个改成 False。
POWER_ENTITY_INVERTED = True