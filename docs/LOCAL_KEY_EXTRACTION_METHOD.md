*[Русская версия](LOCAL_KEY_EXTRACTION_METHOD.ru.md)*

# Extracting the Tuya local_key from the Danfoss Ally app

How to obtain the `local_key` of a Danfoss Ally Gateway for local control over
the Tuya protocol. No reverse engineering of the native crypto code, and no
need to make the app send a command.

## What you actually need

```
device_id: <GATEWAY_DEVICE_ID>   (Danfoss Ally Gateway)
local_key: <GATEWAY_LOCAL_KEY>   (16 characters, ASCII, as-is, not hex)
```

The Icon2 RT thermostats and the Icon2 Controller have no separate `local_key`
and do not need one. They are Zigbee sub-devices behind the gateway (their
JSON record carries `"communicationNode":"<GATEWAY_DEVICE_ID>"` and
`"devAttribute":2048`), and locally they are addressed with the gateway's key
plus their own `nodeId` (also called `cid`, or `device_cid` in tuya_local).
One key for the whole system.

The `nodeId` of every sub-device arrives in the `deviceTopo` field alongside
the normal device list, so you do not need to open each thermostat's card.
Opening the gateway's card once is enough.

The RT numbering in the app does not match the `nodeId` suffix. The `-01`,
`-02`, ... suffix is the Zigbee pairing order, not the thermostat number. Take
it strictly from the dump.

| Device | device_id | cid (nodeId) |
|---|---|---|
| Ally Gateway | `<GATEWAY_DEVICE_ID>` | none (the gateway is not added as its own device, it has no DPS) |
| Icon2 Controller | `<ICON2_CONTROLLER_DEVICE_ID>` | `<ZIGBEE_BASE_NODE_ID>` |
| Icon2 RT | `<RTn_DEVICE_ID>` | `<ZIGBEE_BASE_NODE_ID>-0N` |

For every record `host = <GATEWAY_LAN_IP>`, `local_key = <GATEWAY_LOCAL_KEY>`,
`protocol_version = 3.5`.

## Where the key lives and why you cannot just read it off disk

- The app's MMKV stores (`/data/data/com.danfoss.ally/files/thingmmkv/`) are
  encrypted (entropy around 8 bits/byte). Passively reading the disk without a
  running app does not give you the key.
- `RKStorage` (React Native AsyncStorage, SQLite) and `shared_prefs/*.xml` do
  not contain the key.
- In decrypted form the key only exists in the RAM of the running process,
  inside the device's JSON record from the Tuya SDK's local cache (the
  `"localKey":"..."` field).

It first looked as if the key only appears in memory the moment a command is
sent to the device (the native `mbedtls_aes_setkey_enc/dec` call in
`libmbedcrypto.so`), and sending a command reliably crashed the app on the
x86 emulator (the APK ships only `arm64-v8a`/`armeabi-v7a`, running through the
`libhoudini.so` translator). In fact `localKey` is loaded into the device
model just by opening the device card, without pressing any control. The AES
hook and the crash path are not needed.

## Prerequisites

- A rooted Android with `com.danfoss.ally` installed and logged in. An x86
  emulator (LDPlayer was used) or a real phone both work.
- `adb` with root access (`adb shell su -c ...` works).
- `frida-server` on the device, started as root
  (`su -c '/data/local/tmp/frida-server &'`).
- On the host, `pip install frida`. The client major version must match the
  `frida-server` version (17.x was used).

## Method

1. Start the app and wait until the device list has loaded and shows live data
   (real temperatures, not empty tiles).
   ```
   adb shell am start -n com.danfoss.ally/com.smart.ThingSplashActivity
   ```
2. Open the gateway's card (tap its tile in the list). That is the trigger
   that loads its `localKey` into memory. Do not press anything inside the
   card.
3. Find the process PID.
   ```
   adb shell su -c 'ps -A' | grep danfoss
   ```
   You want the main process (`Ally` / `com.danfoss.ally`), not `:monitor`.
   That is a separate child process without the data you need.
4. Attach Frida by PID (not by package name; Frida sees the process as
   `Ally`), scan the process memory across all `r--`/`rw-` regions for the
   string `"localKey":"` (or for a known `device_id`), and for every match dump
   a few kilobytes of surrounding text. That is where the full device JSON
   record sits, including `devId`, `localKey`, and `deviceTopo` with the
   sub-devices' `nodeId`.
5. Filter the matches. The `localKey` value next to the gateway's `devId` is
   the key you want. Records with self-referential values (`"devId":"devId"`)
   are JSON-schema fragments, skip them.

On recent Frida, memory is read with the pointer method
`ptr.readByteArray(len)`. `Memory.readByteArray()` is deprecated and fails
with `TypeError: not a function`.

## Verifying the key

The key is confirmed two independent ways.

1. Cryptographically. On protocol 3.5 the session handshake (negotiating the
   session key through a key-encrypted nonce exchange) completes ("Session key
   negotiate success!"). With a wrong key the nonce decryption yields garbage
   and the handshake fails immediately.
2. Functionally. Live status of a sub-device through the gateway:
   ```python
   import tinytuya
   gw = tinytuya.Device(GATEWAY_ID, IP, LOCAL_KEY, version=3.5)
   sub = tinytuya.Device(RT_DEVICE_ID, IP, LOCAL_KEY, version=3.5,
                         cid=RT_NODE_ID, parent=gw)
   sub.status()  # -> {'dps': {...}, 'cid': RT_NODE_ID, ...}
   ```
   In the reply `"24"` (air temperature, /10) and `"34"` (battery, %) should
   match what the app shows.

Note. The gateway itself replies to `status()` without a `cid` with
`{'Error': 'Invalid JSON Response from Device', 'Err': '900', ...}`. That is
not a key error, the session establishes fine. The gateway has no DPS of its
own (`"dps":{}` in its record, an empty `statusSchemaList`), it is a pure
bridge. You have to query a sub-device with its `cid`.

If Home Assistant already has tuya_local (the make-all/tuya-local project, not
rospogrigio's LocalTuya), its manual add form has a `device_cid` field. Each
thermostat is added as `device_id` + `host` + the gateway's `local_key` +
`protocol_version=3.5` + its own `device_cid`. Do not add the gateway as its
own device.

## Gotchas

- The app process can die between scan runs
  (`frida.NotSupportedError: unable to write to process memory: No such
  process` while the PID is still live in `ps`). Re-running the scan usually
  works, it goes through on the second try.
- If the app dies after Frida attaches, restart it, open the gateway's card
  again and retry. The data reappears in memory once the card is open.
