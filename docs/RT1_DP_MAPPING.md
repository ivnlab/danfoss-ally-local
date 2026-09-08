*[Русская версия](RT1_DP_MAPPING.ru.md)*

# Icon2 RT datapoint (DP) mapping (<RT1_DEVICE_ID>, cid <ZIGBEE_BASE_NODE_ID>-01)

Sources:
1. The official Tuya product schema `hlbcgne6` (app cache) - the only source
   that actually shows the raw DP numbers and their names, but it only covers
   9 generic fields.
2. `mtrab/danfoss_ally` (custom_components/danfoss_ally/*.py) - a mature,
   long-used HACS integration.
3. `mtrab/pydanfossally` - the library the integration is built on; in
   particular `docs/writable-properties-research.md` (live write/rollback
   testing against the real Danfoss API, separately on Ally radiators and on
   Icon2 RT) and `pydanfossally/const.py` (`SETPOINT_CODES`, `BOOLEAN_CODES`,
   `PASSTHROUGH_CODES`, `MODE_TO_SETPOINT_CODE`).

Important limitation of sources 2 and 3. They work with the named Danfoss
cloud API (`{"code": "...", "value": ...}`), which already proxies Tuya - the
raw DP numbers are not there at all, the number-to-name translation happens
entirely inside the Tuya/Danfoss backend and is not publicly documented
anywhere. So the only working way to map against the local protocol (the raw
DP numbers as the gateway hands them out over the LAN) is live comparison:
change a value in the app/HA and watch which raw DP changed. Sources 2 and 3
give an authoritative list of names and the read/write semantics for each -
which fields can actually be changed, which are read-only - which sharply
narrows the search space when mapping.

## Confirmed by the official Tuya schema (functionSchemaList/statusSchemaList)

| DP | Name | Type | Range |
|---|---|---|---|
| 1 | switch | Boolean | **clarified below: not a general thermostat on/off, but the Pre-heat toggle** |
| 2 | **mode** | Enum | confirmed by live test 2026-08-04: `leaving_home`/`at_home`/`pause`/`holiday`/`manual`. The official Tuya schema only listed [holiday, manual] - incomplete, there are more real values |
| 16 | temp_set | Integer /10 | 4.0-35.0C, fallback setpoint for models without separate per-mode setpoints |
| 18 | upper_temp | Integer /10 | 20.0-35.0C |
| 27 | lower_temp | Integer /10 | 4.0-20.0C |
| 30 | child_lock | Boolean | |
| 34 | battery_percentage | Integer | 0-100% |
| 44 | factory_reset | Boolean | (write-only, do not expose in UI) |
| 45 | fault | Bitmap | |

## Confirmed by matching against mtrab/danfoss_ally (high confidence)

| DP | Live value | Field (per mtrab code) | Rationale |
|---|---|---|---|
| 3 | "Heat"/"heat_active" | `work_state` | exact match with the enum in climate.py; confirmed 2026-08-04 by a live "Heat" to "heat_active" transition when active heating started |
| **140** | **"Inactive" to "active"** | **`output_status`** (thermal actuator) | Checked 2026-08-04: RT6 target raised to 32.5C (above current), the actuator in the app showed "Open" - DP140 flipped at that exact moment from `"Inactive"` to `"active"` |
| 24 | 265 | `temperature` (air, current, /10) | cross-checked directly with the app: 26.5C |
| **101** | **250** | **`floor_temperature`** (floor, current, /10) | Checked 2026-08-04: live RT6 dump (`'24':256,'101':250`) matched one-for-one against the HA screenshot at that moment ("Air T 25.6C", "Floor T 25.0C") - both numbers matched at once |
| **106** | **740** | **`humidity_value`** | Checked 2026-08-04: RT6 dump (`'106':740`) matches the HA screenshot "Humidity: 74.0%" |
| 103 | "0x8041" | `adaptation_runstatus` | format matches, the code does `int(value) & 0x01` / `& 0x02` / `& 0x04` |
| 111 | "Manual" | `setpointchangesource` | the code compares `== "Manual"` literally |

Checked 2026-08-04: the mode was switched to "Away" - `DP 2` showed
`"leaving_home"` (exact match), while **DP 127 disappeared from the status
entirely** (not present in the reply). So `DP 2 = mode` is the right field,
and DP127 is a random/unstable artefact, not used for this. DP127 is unused.

## Per-mode setpoints - confirmed by live test (2026-08-04, RT6)

Three setpoints were changed at once on RT6 in the app (Home 22.0 to 22.5,
Away 19.0 to 19.5, Pause 5.0 to 5.5) - live status was taken via `cid` and
cross-checked. Each setpoint is stored **not in one DP but in several
synchronized copies** (they change together on any change):

| Setpoint | Value | DP (all change together) |
|---|---|---|
| Home (`at_home_setting`) | 22.5C, raw 225 | **16, 113, 118** |
| Away (`leaving_home_setting`) | 19.5C, raw 195 | **109, 112, 119** |
| Pause (`pause_setting`) | 5.5C, raw 55 | **110, 114, 120** |

For reading in HA it does not matter which DP of a group you use - they are
always in sync. For writing it is not yet verified which copy is the
"canonical" field that a command actually needs to go to (possibly any,
possibly only one, with the rest being derived/mirror copies for various
internal structures like the schedule).

This also firmly confirmed: **DP 111 = `setpointchangesource`** - it was
`"Manual"`, and after a change through the app it became `"Externally"`. The
value literally describes the source of the last change (manually on the
thermostat vs remotely) - semantically exactly that field.

## Holiday - architecturally NOT the same kind of preset as Home/Away/Pause

Live test (2026-08-04, all 6 RTs at once): thermostats bound to rooms, pause
lifted, "Holiday to Away to Now" applied with 16.5C. Result - `165` appeared in
DP **115** and **121** synchronously on all 6 thermostats.

Important detail: DP **114**, which in the previous test looked like part of
the "Pause" group (110/114/120=55), **also changed to 165** (except RT3, which
did not catch up - update lag, expected). But DP 110 and 120 stayed at 55
unchanged.

Checked 2026-08-04:
After leaving Holiday and switching RT6 to `leaving_home` (19.5C):
- **DP 114 changed to `195`** (adjusted to the new active mode)
- **DP 115 and DP 121 stayed `165`** (unchanged, even though Holiday is no
  longer active)

That is the isolation: **DP 114 = "currently active setpoint"** (a live
pointer to the value of whichever mode is actually in effect right now - 55
during Pause, 195 during leaving_home, 165 during Holiday). **DP 115 and DP
121 = the real `holiday_setting`** - a stable register, not reset when the
mode changes, holding the set Holiday temperature regardless of what is active
now. (115 and 121 are still two synchronized copies of the same field.)

## DP 1 = the Pre-heat toggle (found from switch.py source, not by guessing)

`custom_components/danfoss_ally/switch.py`:

```python
DanfossAllySwitchDescription(
    key="switch",
    translation_key="pre_heat",
    ...
)
```

So the Danfoss cloud reads/writes a field named `switch` (raw DP **1**) as
"whether pre-heating is enabled for this thermostat" - this is not a general
device on/off (a floor-heating loop has no physical "off" in the usual sense,
so the Tuya generic field was repurposed for Pre-heat). Confirmed by live
test: Pre-heat turned off in HA, DP1 became `False` (it was `True` in all
prior dumps).

The same `switch.py` had the names of a few more toggles - their DP numbers
were initially searched among 106/117/123-141 (see below, conclusion: those
fields physically do not exist on Icon2 RT).

## Fields that do NOT exist on Icon2 RT (only on Ally radiators)

Per `writable-properties-research.md`: the library author had two test
accounts - one with Ally radiators, one with Icon2 RT (the same model). Their
lists of observed fields are different. The following fields appear only in the
Ally radiator account and are absent from the Icon2 RT list - meaning they
physically are not in the data this hardware reports, and searching for their
DP is pointless:

`load_balance_enable`, `radiator_covered`, `heat_available`,
`window_toggle`, `window_state_info`, `mounting_mode_active`, `ctrl_alg`,
`valve_opening`, `load_room_mean`, `OccupiedSetpoint`, `pi_heating_demand`.

## Known field names without a confirmed DP number

The full officially confirmed list for Icon2 RT (from
`writable-properties-research.md`, live testing against the real Danfoss API) -
with read-only/writable marked from there too:

| Field (cloud name) | R/W | DP found? |
|---|---|---|
| `switch` | writable | DP 1 (this is pre_heat, not general power) |
| `mode` | writable | DP 2 |
| `work_state` | **read-only** | DP 3 |
| `temp_set` | writable | DP 16 |
| `upper_temp` | writable | DP 18 |
| `lower_temp` | writable | DP 27 |
| `temp_current` | **read-only** | DP 24 |
| `child_lock` | writable | DP 30 |
| `battery_percentage` | **read-only** | DP 34 |
| `fault` | **read-only** | DP 45 |
| `SetpointChangeSource` | **read-only** | DP 111 |
| `manual_mode_fast` | writable | not found - by analogy with holiday, probably also a separate stable register among the not-yet-mapped ones (102,117,123,124,126,128,129,130,135,137,139,141) |
| `at_home_setting` | writable | DP 16/113/118 (group) |
| `leaving_home_setting` | writable | DP 109/112/119 (group) |
| `pause_setting` | writable | DP 110/120 (group) |
| `holiday_setting` | writable | DP 115/121 (group) |
| "currently active setpoint" (what climate.py computes via `_get_setpoint_for_mode`) | - | DP 114 |
| `switch_state` | writable | not found - together with `switch` it forms the `pre_heating` status; cannot be caught while `switch`(pre_heat)=false, needs a re-test with pre_heat on |
| `floor_temperature` (`MeasuredValue`/`floor_sensor` in the raw API) | **read-only** | DP 101 |
| `humidity_value` | **read-only** | DP 106 |
| `temp_mode` | **read-only** | not found |
| `output_status` (thermal actuator) | **read-only** | **DP 140** - confirmed 2026-08-04, value `"Inactive"`/`"active"` |
| `system_status_water` | **read-only** | not found |

## Summary

Full confirmed set: `switch`=pre_heat (1), `mode` (2), `work_state` (3),
`temperature`/air (24), `floor_temperature`/floor (101), `humidity_value`
(106), "active setpoint" (114), `at_home_setting` (16/113/118),
`leaving_home_setting` (109/112/119), `pause_setting` (110/120),
`holiday_setting` (115/121), `upper_temp` (18), `lower_temp` (27),
`child_lock` (30), `battery_percentage` (34), `fault` (45),
`adaptation_runstatus` (103), `setpointchangesource` (111), `output_status`/
thermal actuator (140).

The only ones missing are `switch_state` and `manual_mode_fast` (both exist on
Icon2 RT per the pydanfossally doc, just not caught in the tests) and
`heat_supply_request` (present in mtrab's code but not mentioned in either of
the research doc's two lists - unclear whether it exists on Icon2 RT at all).
The rest from earlier versions of this section (`mounting_mode_active`,
`ctrl_alg`, `radiator_covered`, `heat_available`, `load_balance_enable`,
`window_toggle`) - see the section above, confirmed absent on this model.
Nothing left over blocks building the config - these are purely diagnostic
fields that do not affect control.
