# 九牧自动校时小程序 BLE 协议还原规格

- 来源：`wx890d0ddb0174a600` v9 解包目录 `static/out/wx890d0ddb0174a600/app`
- 证据文件：本地解包目录中的 `app-service.js`、`app-config.json`（第三方原始源码不随本仓库分发）
- 还原方式：逐行阅读 `pages/index`、`pages/functionPage*`、`utils/util.js`，未做任何猜测；源码未写死的值标为“运行时发现/未知”。

> 结论：这是**广播/连接后动态发现 Service 与 Characteristic** 的私有 BLE 协议；协议里**没有固定 Characteristic UUID**，只有固定 Service UUID 与“按 properties 选读写/通知特性”的规则。五个校时帧都是**二进制原始字节**，无 BCD、无加密、无签名，只有 14 字节帧和 9 字节帧带校验和。

## 1. 广播匹配与设备分支

入口页按 `getBLEDeviceServices()` 返回的 Service UUID 子串匹配，再按设备名分流到不同页面，见本地解包源码 `app-service.js` L1192。

| Service UUID（源码匹配串） | 设备名条件（`data.name`） | 跳转页面 | 帧函数 | 备注 |
|---|---|---|---|---|
| `0000FF00-0000-1000-8000-00805F9B34FB` | `YHD-MODULE` 或 `JM_Cabinet` | `pages/functionPage/functionPage` | `timeToBytes`（6 B） | 主分支 |
| `0000FF00-...` | 其它名字 | `pages/functionPageLed/functionPageLed` | `timeToBytes2`（10 B） | LED 兜底 |
| `0000FFE0-...` | `JM_Cabinet` | `pages/functionPageMJL/functionPageMJL` | `timeToBytes4`（8 B，ASCII 包裹） | MJL |
| `0000FFE0-...` | 其它名字 | `pages/functionPageLed/...` | `timeToBytes2`（10 B） | LED 兜底 |
| `00009900-...` | `JM_Cabinet` 或 `BXICHENG` | `pages/functionPageQingZhou/functionPageQingZhou` | `timeToBytes3`（14 B） | 青洲 |
| `00009900-...` | 其它名字 | `pages/functionPageLed/...` | `timeToBytes2`（10 B） | LED 兜底 |
| `0000FFF0-...` | 任意名字 | `pages/functionPageWST/functionPageWST` | `timeToBytes5`（9 B） | WST |

设备名白名单（源码 `data` 中硬编码）：`YHD-MODULE`、`JM_Cabinet`、`JM_LEDM1`、`BXICHENG`、`BT24`。其中 `JM_LEDM1`、`BT24` 在源码里**没有专门分支**，只会落到 LED 兜底页。

## 2. 连接与特征选择流程

源码顺序（以 `pages/index/index` → 功能页为例）：

1. `wx.openBluetoothAdapter`
2. `wx.startBluetoothDevicesDiscovery({services: [], allowDuplicatesKey: true})`
3. `wx.onBluetoothDeviceFound` 按名称/`localName` 收集设备
4. `wx.createBLEConnection({deviceId})`
5. `wx.getBLEDeviceServices({deviceId})` → 按上表 Service UUID 匹配 → `navigateTo` 功能页（把 `deviceId`、`serviceId`、`name` 放进 URL）
6. 功能页 `onLoad`：`wx.getBLEDeviceCharacteristics({deviceId, serviceId})`
7. 发现 `properties.notify`/`indicate` 时立即 `wx.notifyBLECharacteristicValueChange({state: true, ...})`
8. 用户点“校时”：构造帧 → `wx.writeBLECharacteristicValue({value: 帧.slice(0, 20)})`
9. 部分页面紧接着 `wx.readBLECharacteristicValue({characteristicId: 写入特性})`（不是读特性，源码就是这么写的）
10. 收到任意 notify → 只把日志显示为“校时成功”，**不解析应答内容**
11. 用户手动“断开”按钮 → `wx.closeBLEConnection`；功能页 `onUnload` **没有**自动断开

### 2.1 Characteristic 选择规则（UUID 不写死）

| 分支页面 | 遍历范围 | read 特性 | write 特性 | notify 特性 | 写后是否 read |
|---|---|---|---|---|---|
| `functionPage` | 只取前 **2** 个 characteristic（`for(a=0;a<2;a++)`） | 第一个 `properties.read` | 第一个 `properties.write` | 第一个 `notify`/`indicate` | 否 |
| `functionPageLed` | 全部 | 第一个 `read` | 第一个 `write` | 每次遇到 notify 都覆盖并重新订阅（最终为最后一个） | 是，读**写入特性** |
| `functionPageQingZhou` | 全部 | 同上 | 同上 | 同上 | 是，读**写入特性** |
| `functionPageMJL` | 只取前 **1** 个 characteristic（`for(a=0;a<1;a++)`） | 第一个 `read` | 第一个 `write` | 第一个 notify | 是，读**写入特性** |
| `functionPageWST` | 全部 | 同上 | 同上 | 同上 | 是，读**写入特性** |

源码只检查 `properties.write`，**完全没有检查 `writeNoResponse` / `write-without-response`**。因此：
- 真实设备上的写特性 UUID、是否支持无响应写、notify 特性 UUID，都必须上机扫描确认（见 §6）。
- `wx.writeBLECharacteristicValue` 的底层写类型由微信/系统实现决定，源码没有显式控制。
- 20 字节截断：除 MJL 外都执行 `value.slice(0, 20)`；所有原始帧 ≤14 B，实际不会截断。MJL 写入 ASCII 串 `"*"+hex+"*"`，8 字节帧对应 18 B，也未截断。

### 2.2 时序、重试、延时

| 项目 | 源码事实 |
|---|---|
| 是否必须先订阅 notify 再写 | 代码会订阅 notify，但**没有任何等待订阅完成的逻辑**；`notifyBLECharacteristicValueChange` 后立即允许用户点按钮 |
| 写后是否等应答再发下一帧 | **不等**。每次校时只有**一帧**写入，不存在多帧序列 |
| 是否校验应答内容 | **不校验**。收到任意 notify 就显示“校时成功” |
| 重试 | **无** |
| 写间隔/延时 | **无有效延时**。`setTimeout(function(){}, 150)` 是空回调，没有作用 |
| 超时 | 只有 UI 的 `showLoading` 3 s、`showToast` 2 s；BLE 无超时处理 |

## 3. 校时帧逐字节规格

所有时间字段都取**手机本地时间**（`new Date()` / `getHours()` 等），无 UTC、无时区转换、无 NTP。年份偏移和校验和全部按源码公式。

### 3.1 `timeToBytes`（FF00 主分支，6 字节）

源码：本地解包源码 `app-service.js` 中的 `utils/util.js` L1186

| 偏移 | 值 | 说明 |
|---|---|---|
| 0 | `0xFC` | 帧头 |
| 1 | `(hour + minute + second) & 0xFF` | 时分秒之和（最大 141，源码不会溢出） |
| 2 | `hour` | 0–23 |
| 3 | `minute` | 0–59 |
| 4 | `second` | 0–59 |
| 5 | `0xFC` | 帧尾 |

**不含年/月/日**；函数参数 `e` 未被使用。

### 3.2 `timeToBytes2`（LED 兜底，10 字节）

源码：本地解包源码 `app-service.js` L1186

| 偏移 | 值 | 说明 |
|---|---|---|
| 0 | `0xFC` | 帧头 |
| 1 | `(yearOffset + month + day) & 0xFF` | yearOffset = 年 - 2000 |
| 2 | `yearOffset` | 年 - 2000 |
| 3 | `month` | 1–12 |
| 4 | `day` | 1–31 |
| 5 | `weekday` | JS `getDay()`：周日=0，周一=1 … 周六=6 |
| 6 | `hour` | 0–23 |
| 7 | `minute` | 0–59 |
| 8 | `second` | 0–59 |
| 9 | `0xFC` | 帧尾 |

无独立校验和；偏移 1 只是字段和。

### 3.3 `timeToBytes3`（青洲，14 字节）

源码：本地解包源码 `app-service.js` L1186

| 偏移 | 值 | 说明 |
|---|---|---|
| 0 | `0x55` | 帧头 |
| 1 | `0x01` | 固定 |
| 2 | `0x0B` | 固定 |
| 3 | `0x71` | 固定 |
| 4 | `0x07` | 固定 |
| 5 | `year - 1792` | **偏移 1792**，不是 2000 |
| 6 | `month` | 1–12 |
| 7 | `weekday` | JS 周日=0 |
| 8 | `day` | 1–31（注意在 weekday 之后） |
| 9 | `hour` | 0–23 |
| 10 | `minute` | 0–59 |
| 11 | `second` | 0–59 |
| 12 | `(0xD9 + yearOffset + month + weekday + day + hour + minute + second) & 0xFF` | **校验和**，按单字节回绕 |
| 13 | `0xAA` | 帧尾 |

### 3.4 `timeToBytes4`（MJL，8 字节 + ASCII 包裹）

源码：本地解包源码 `app-service.js` L1186；包裹逻辑见 `pages/functionPageMJL` L1207

| 偏移 | 值 | 说明 |
|---|---|---|
| 0 | `(yearOffset + month + day) & 0xFF` | yearOffset = 年 - 2000；**无帧头** |
| 1 | `yearOffset` | 年 - 2000 |
| 2 | `month` | 1–12 |
| 3 | `day` | 1–31 |
| 4 | `weekday` | JS 周日=0 |
| 5 | `hour` | 0–23 |
| 6 | `minute` | 0–59 |
| 7 | `second` | 0–59 |

写入前被转换成 **ASCII 文本**：`"*" + 小写十六进制串 + "*"`（每个字节两位，`ab2hext` 补零）。例如 8 字节帧 `28 1A 0B 03 02 0B 20 37` → `*281a0b03020b2037*`（18 字节）。

### 3.5 `timeToBytes5`（WST，9 字节）

源码：本地解包源码 `app-service.js` L1186

| 偏移 | 值 | 说明 |
|---|---|---|
| 0 | `0xA5` | 帧头 |
| 1 | `0x02` | 固定 |
| 2 | `0x05` | 固定 |
| 3 | `0x05` | 固定 |
| 4 | `0xD1` | 固定 |
| 5 | `hour` | 0–23 |
| 6 | `minute` | 0–59 |
| 7 | `second` | 0–59 |
| 8 | `(0xDD + hour + minute + second) & 0xFF` | **校验和**；不含年月日 |

### 3.6 测试帧（源码 `OnClickTest`）

| 函数 | 字节 |
|---|---|
| `sendTestToBytes` | `FC 19 19 00 00 FC` |
| `sendTestToBytes2` | `FC 00 00 00 00 19 00 00 00 FC` |

## 4. 示例帧（固定时间戳）

取本地时间 **2026-11-03 11:32:55**（周二，`getDay()=2`）：

| 帧 | 十六进制 | 说明 |
|---|---|---|
| 6 B `timeToBytes` | `FC 62 0B 20 37 FC` | 62 = 11+32+55 |
| 10 B `timeToBytes2` | `FC 28 1A 0B 03 02 0B 20 37 FC` | 28 = 26+11+3 |
| 14 B `timeToBytes3` | `55 01 0B 71 07 EA 0B 02 03 0B 20 37 35 AA` | EA = 2026-1792；35 = 0xD9+234+11+2+3+11+32+55 |
| 8 B `timeToBytes4` | `28 1A 0B 03 02 0B 20 37` | MJL 实际写入 `*281a0b03020b2037*` |
| 9 B `timeToBytes5` | `A5 02 05 05 D1 0B 20 37 3F` | 3F = 0xDD+11+32+55 |

> 若 HA 与设备所在时区不同，按设备所在时区的本地时间计算；源码使用的是手机本地时间。

## 5. 分支差异汇总

| 分支 | 帧 | 帧长 | 写入前处理 | 特征遍历限制 | 写后 read | 订阅 notify |
|---|---|---|---|---|---|---|
| FF00 主 | `timeToBytes` | 6 B | `slice(0,20)` | 前 2 个 | 否 | 是 |
| LED 兜底 | `timeToBytes2` | 10 B | `slice(0,20)` | 全部 | 是 | 是 |
| 9900 青洲 | `timeToBytes3` | 14 B | `slice(0,20)` | 全部 | 是 | 是 |
| FFE0 MJL | `timeToBytes4` | 8 B → 18 B ASCII | `"*"+hex+"*"`，不 slice | 前 1 个 | 是 | 是 |
| FFF0 WST | `timeToBytes5` | 9 B | `slice(0,20)` | 全部 | 是 | 是 |

## 6. 源码未确定、需要上机确认的点

1. 写/通知/读 Characteristic 的真实 UUID：运行时按 properties 选，源码没有常量。
2. 写特性是否支持 `write-without-response`：源码没查；HA 侧按 properties 自动选择 `response=True/False`。
3. 设备是否必须在 notify 订阅完成后才接受写入：源码不等；若真机要求，HA 侧需加延时/等待。
4. notify 应答的真实字节格式：源码不解析，任意 notify 都当成功。
5. 广播里是否携带上述 Service UUID 或设备名：决定 HA 能否自动发现（见 README/方案说明）。
6. 设备时区：源码用手机本地时间，设备端是否按本地时区解释年月日时分秒需实测。
