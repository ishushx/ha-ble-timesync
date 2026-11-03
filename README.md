# ha-ble-timesync

把微信小程序「小程序九牧自动校时」（`wx890d0ddb0174a600` v9）的 BLE 校时协议接入 Home Assistant。

- **推荐架构**：ESPHome 只做纯 `bluetooth_proxy`（不在 YAML 写 MAC）→ HA 自定义集成自动发现广播 → 用户确认 → 动态枚举 GATT → 写校时帧。
- **不包含**小程序解包出来的第三方源码；只包含从协议行为还原的规格与本项目代码。
- **不包含任何密钥/个人信息**；ESPHome 示例中的 API key 是仅供编译的全零占位符。

## 文件结构

```
custom_components/jiumu_ble_sync/   HA 自定义集成
  manifest.json                     bluetooth 依赖 + Service UUID/设备名匹配器
  config_flow.py                    广播自动发现 + 确认 + 手动兜底
  sync.py                           连接、动态选特征、写帧、等 notify
  protocol.py                       5 种校时帧构造
  const.py                          协议常量
  coordinator.py / button.py / sensor.py
esphome/
  jiumu-ble-proxy.yaml              纯蓝牙代理（推荐，无 MAC）
  jiumu-ble-client-fallback.yaml    ble_client 硬编码兜底（备选，需手填 MAC）
examples/ha_automations.yaml        每日/启动后校时示例
protocol-spec.md                    完整协议规格（逐字节）
```

## 协议速查

| Service | 设备名 | 分支 | 帧 |
|---|---|---|---|
| `FF00` | `YHD-MODULE` / `JM_Cabinet` | general | 6 B：`FC (h+m+s) h m s FC` |
| `FF00` | 其它 | led | 10 B：`FC (y+m+d) y m d w h m s FC`，y=年-2000 |
| `FFE0` | `JM_Cabinet` | mjl | 8 B：`(y+m+d) y m d w h m s`，写成 ASCII `*hex*` |
| `FFE0` | 其它 | led | 10 B |
| `9900` | `JM_Cabinet` / `BXICHENG` | qingzhou | 14 B：`55 01 0B 71 07 (年-1792) m w d h m s (0xD9+…) AA` |
| `9900` | 其它 | led | 10 B |
| `FFF0` | 任意 | wst | 9 B：`A5 02 05 05 D1 h m s (0xDD+h+m+s)` |

示例（2026-11-03 11:32:55，周二）：

| 分支 | 字节 |
|---|---|
| general | `FC 62 0B 20 37 FC` |
| led | `FC 28 1A 0B 03 02 0B 20 37 FC` |
| qingzhou | `55 01 0B 71 07 EA 0B 02 03 0B 20 37 35 AA` |
| mjl 实际写入 | `*281a0b03020b2037*` |
| wst | `A5 02 05 05 D1 0B 20 37 3F` |

时序要点：

- 源码先订阅 notify，再写；**每次只写一帧**；不校验 notify 内容，收到任意 notify 即提示成功；无重试、无写间隔。
- 写入/通知 **Characteristic UUID 源码没有写死**，运行时按 `properties` 选；本集成同样动态枚举。
- 源码只检查 `properties.write`，不检查 `write-without-response`；本集成会检查，并自动选择 `response=True/False`。
- 完整逐字节说明见 [protocol-spec.md](protocol-spec.md)。

## 自动发现架构

```
BLE 设备广播
   │  (Service UUID / 设备名)
   ▼
ESP32 bluetooth_proxy（active: true）
   │  转发 advertisement + 提供 GATT 连接通道
   ▼
HA bluetooth 集成 (habluetooth)
   │  manifest.json bluetooth matchers
   ▼
config_flow.async_step_bluetooth(BluetoothServiceInfoBleak)
   │  显示名称 / MAC / 自动判断分支
   ▼
用户点“确认” → 创建 config entry → button + last_sync sensor
   │
   ▼
sync.py: async_ble_device_from_address(connectable=True)
   → BleakClient 经代理连接
   → 动态枚举 service/characteristic
   → 写帧 → 等 notify → 断开
```

> 当前 HA 的发现 API 名称是 `BluetoothServiceInfoBleak`（旧资料里可能写作 `BluetoothServiceInfoBleDevice`）和 `bluetooth.async_register_callback`。本集成使用更标准的 **manifest matcher + `async_step_bluetooth`** 路径，等价于“匹配广播后弹确认”，不需要自己注册全局回调。

### 自动发现 vs 手动填写边界

| 项目 | 自动 | 手动 |
|---|---|---|
| 设备 MAC/地址 | ✅ HA 广播里的 address | 仅在设备不广播时手填 |
| 设备名 | ✅ advertisement `local_name` | 地址作为标题 |
| 协议分支 | ✅ Service UUID + 名称规则，可在确认页修正 | 下拉选择 |
| Service UUID | ✅ 连接后枚举 | 同左 |
| 写/通知 Characteristic UUID | ✅ 连接后按 properties 枚举 | 同左 |
| 设备不在广播里/名称不匹配 | ❌ 不会触发发现卡片 | ✅ 手动添加 |

## 安装 HA 自定义集成

1. 把 `custom_components/jiumu_ble_sync` 复制到 HA 配置目录：
   ```
   /config/custom_components/jiumu_ble_sync/
   ```
2. 重启 Home Assistant。
3. 确保「设置 → 设备与服务 → Bluetooth」已加载，并且至少有一个 ESPHome 代理在线（或本机蓝牙适配器）。
4. 设备上电并靠近代理后，HA 会自动弹出“发现九牧蓝牙设备”卡片；点确认即可。
5. 若没有弹出：设置 → 设备与服务 → 添加集成 → 搜索 `Jiumu BLE Time Sync`，用“手动添加”兜底。

### 实体与服务

- `button.<device>_sync_now` / 名称“立即校时”：按一下立即校时。
- `sensor.<device>_last_sync` / 名称“最后校时时间”：最近一次成功写入后的时间戳。
- 服务 `jiumu_ble_sync.sync_time`：调试用，参数 `address`、`model`、`wait_notify`，会返回 `payload_hex`、`notify_ack`、`notifications`、`write_uuid` 等。

## ESPHome 蓝牙代理

使用 [esphome/jiumu-ble-proxy.yaml](esphome/jiumu-ble-proxy.yaml)。关键点：

- `bluetooth_proxy: active: true`：允许 HA 建立 GATT 连接。
- `esp32_ble_tracker` 的 `active: true`：拿到 scan response 中的名称/Service UUID。
- `connection_slots: 3`，`esp32_ble: max_connections: 3`：官方上限为 3 个并发主动连接；不要超过 5。
- 使用 **ESP-IDF** 框架（Arduino 内存占用高、代理表现差）。
- 推荐 ESP32-S3（内存余量更大）；ESP32-C3 可用但槽位/内存更紧。
- 不要开 `web_server`，代理容易内存不足。
- 柜体/工业场景：把代理放在柜体附近，或用以太网/PoE 板；Wi-Fi 代理不要随意改 scan interval/window。

## HA 自动化示例

见 [examples/ha_automations.yaml](examples/ha_automations.yaml)：每天 03:00、HA 启动后 5 分钟、以及调试用服务调用。

## 真机验证步骤

1. **看广播匹配**：ESPHome 日志设为 `DEBUG`，应出现 `esp32_ble_tracker` 扫描到的设备；HA 日志（设置 → 系统 → 日志）搜索 `jiumu_ble_sync`，确认 `async_step_bluetooth` 被触发。
2. **看连接与特征**：把 `custom_components.jiumu_ble_sync` 日志级别调到 `DEBUG`（`configuration.yaml` 的 `logger.logs`），按“立即校时”，日志会打印 `service/family/model/write/notify/read/response` 和 `payload`。
3. **看写帧成功**：`write payload: ...` 与源协议示例帧一致；若 `notify_ack: false` 但无异常，说明写入已发出但设备没回 notify。
4. **抓 notify 原始字节**：本集成在 `sync.py` 的 `_on_notify` 里把原始字节 hex 记录到 `DEBUG` 日志，同时通过服务返回值 `notifications` 暴露。
5. **常见异常**：
   - `当前不可连接`：代理离线/未开 `active: true`/设备已被其它主机连接。
   - `未发现 FF00/FFE0/9900/FFF0 服务`：Service UUID 与广播/设备不一致，或连接到了错误设备。
   - `没有可写 characteristic`：设备要求加密配对、或特征在更后面的序号（源码的 `CHAR_LIMIT` 可能过严，可改 `const.py`）。
   - `write-without-response` 不支持/写入失败：日志会显示实际选中的 write UUID 与 response 模式。
   - notify 无响应：先确认 `notify_uuid` 正确；尝试 `notify_settle` 加大；或在 `sync.py` 里改成写后延时。
6. **首次建议日志级别**：ESPHome `DEBUG`；HA `custom_components.jiumu_ble_sync: DEBUG`；必要时 `homeassistant.components.bluetooth: DEBUG`。

## 限制与已知问题

1. **自动发现依赖广播**：设备必须在广播中包含上述 Service UUID 或精确设备名。若设备只在连接后暴露 Service、或广播名与小程序里的名字不同，自动发现不会触发，只能手动添加。这是自动发现与手动填写的明确边界。
2. **不能运行时改 MAC 的 `ble_client`**：ESPHome `ble_client` 的 `mac_address` 是编译期必填项（官方文档明确 Required, MAC Address），无法按扫描结果动态连接，因此本方案不用它做主路径。
3. **`ble_client` 与 `bluetooth_proxy` 共存**：两者共享 ESP32 BLE 连接槽（`esp32_ble: max_connections`），官方建议总量不超过 5，主动连接默认上限 3；同时 `ble_client` 固定 MAC，不能自动发现。纯代理方案更稳。
4. **notify 时序**：源码不等订阅完成；本集成在 `start_notify` 后加 0.2 s 安全延时。若真机要求更长，改 `sync.py` 的 `NOTIFY_SETTLE_SECONDS`。
5. **写类型**：本集成优先 `write`（带响应），否则 `write-without-response`。若真机只接受无响应写，可改 `sync.py`。
6. **时区**：协议使用本地时间；HA 的时区必须与设备所在时区一致。
7. **连接槽**：一个 ESP32 代理最多 3 个主动连接；多个柜体同时校时需要错开或增加代理。
8. **HA 版本**：使用 `SupportsResponse`、`BluetoothServiceInfoBleak`，建议 HA 2024.6+。

## 安全说明

- 协议无加密、无签名、无凭证；任何能连上设备的 BLE 客户端都可发校时帧。
- 仓库内没有小程序原始解包代码，也没有 Wi-Fi/API/OTA 密钥；ESPHome 示例中的 `api_key` 是全零占位符，部署前必须替换。
