"""Constants for the Jiumu BLE time sync integration."""

DOMAIN = "jiumu_ble_sync"

CONF_ADDRESS = "address"
CONF_MODEL = "model"
CONF_NAME = "name"
CONF_WAIT_NOTIFY = "wait_notify"

MODEL_AUTO = "auto"
MODEL_GENERAL = "general"
MODEL_LED = "led"
MODEL_QINGZHOU = "qingzhou"
MODEL_MJL = "mjl"
MODEL_WST = "wst"

MODELS = [
    MODEL_AUTO,
    MODEL_GENERAL,
    MODEL_LED,
    MODEL_QINGZHOU,
    MODEL_MJL,
    MODEL_WST,
]

MODEL_LABELS = {
    MODEL_AUTO: "自动识别（连接后按 Service/设备名判断）",
    MODEL_GENERAL: "FF00 主分支（6 字节帧）",
    MODEL_LED: "LED 兜底（10 字节帧）",
    MODEL_QINGZHOU: "9900 青洲（14 字节帧）",
    MODEL_MJL: "FFE0 MJL（8 字节帧，ASCII 包裹）",
    MODEL_WST: "FFF0 WST（9 字节帧）",
}

# 源码 app-service.js L1192 中 index 页使用的完整 128-bit Service UUID。
SERVICE_UUIDS = {
    "ff00": "0000ff00-0000-1000-8000-00805f9b34fb",
    "ffe0": "0000ffe0-0000-1000-8000-00805f9b34fb",
    "9900": "00009900-0000-1000-8000-00805f9b34fb",
    "fff0": "0000fff0-0000-1000-8000-00805f9b34fb",
}

# 源码 index 页 data 中硬编码的设备名。
DEVICE_NAMES = [
    "YHD-MODULE",
    "JM_Cabinet",
    "JM_LEDM1",
    "BXICHENG",
    "BT24",
]

# 源码中每页只遍历前 N 个 characteristic；None 表示全部。
CHAR_LIMIT = {
    MODEL_GENERAL: 2,
    MODEL_LED: None,
    MODEL_QINGZHOU: None,
    MODEL_MJL: 1,
    MODEL_WST: None,
}

# 源码中写入后立即 readBleCharacteristicValue 的分支。
READ_AFTER_WRITE = {
    MODEL_GENERAL: False,
    MODEL_LED: True,
    MODEL_QINGZHOU: True,
    MODEL_MJL: True,
    MODEL_WST: True,
}
