# Danfoss Icon2 (Local)

*[Русская версия](README.ru.md)*

A Home Assistant custom integration for **Danfoss Icon2 RT floor-heating
thermostats**, controlled entirely over the **local Tuya protocol** through
the Danfoss Ally Gateway - no dependency on Danfoss's cloud API, and no
[`tuya_local`](https://github.com/make-all/tuya-local) HACS integration
required.

It's a from-scratch, home-specific integration: the raw datapoint (DP)
mapping was reverse-engineered by hand (see [`docs/`](docs/)), since no
public project had done this for the local protocol before - only for
Danfoss's cloud API (see [Credits](#credits)).

## Why local instead of cloud?

The obvious alternative, [`mtrab/danfoss_ally`](https://github.com/mtrab/danfoss_ally),
works well but depends on Danfoss's cloud being reachable. This integration
talks to the gateway directly over the LAN via [`tinytuya`](https://github.com/jasonacox/tinytuya),
so heating control keeps working even if the internet or Danfoss's servers
are down.

## What's implemented

- **`climate`** - one thermostat entity per RT: Home / Away / Pause / Holiday
  presets, plus a Manual mode with direct temperature control.
- **`sensor`** - floor temperature, humidity, battery, setpoint-change
  source, adaptation-run status.
- **`binary_sensor`** - thermal actuator, fault, setpoint-changed-locally,
  child lock status.
- **`number`** - upper/lower temperature limits and per-preset setpoints
  (Home/Away/Pause/Holiday), editable directly.
- **`switch`** - pre-heat enable.
- **`lock`** - child lock (writable, unlike the cloud integration).

Everything (gateway address/credentials, the 6 RT device IDs) is
hardcoded per-home in `credentials.py` - see [Setup](#setup). This is a
single-home integration, not a general-purpose one; there's no config
form.

## Setup

> **Need your gateway's `local_key`?** Use
> [**get-key-danfoss-ally**](https://github.com/ivnlab/get-key-danfoss-ally) -
> it extracts it (and the RT `device_id`/`cid` table) automatically from the
> Danfoss Ally app's own memory and prints a ready-to-paste snippet. Requires
> a rooted Android device - see its README for details.

1. Copy `custom_components/danfoss_local/` into your Home Assistant
   `config/custom_components/` folder.
2. Copy `credentials.example.py` to `credentials.py` (same folder) and
   fill in your gateway's `local_key`, device ID, LAN IP, and each RT's
   `device_id`/`cid` (see the callout above). For background on *why* this
   works, see
   [`docs/LOCAL_KEY_EXTRACTION_METHOD.md`](docs/LOCAL_KEY_EXTRACTION_METHOD.md).
   See [`docs/RT1_DP_MAPPING.md`](docs/RT1_DP_MAPPING.md) for how the raw
   datapoint numbers were mapped (useful if your device reports different
   DPs).
3. Restart Home Assistant.
4. Settings → Devices & Services → Add Integration → "Danfoss Icon2".

## Known limitations

- The Manual-mode setpoint (`manual_mode_fast`) and the named presets'
  own setpoints share dp 114 as the "currently active setpoint" mirror;
  writing it requires the mode (dp 2) to already be Manual, or the value
  gets ignored (see `coordinator.py`/`climate.py` for the exact write
  logic - this took a lot of live testing to get right).
- The `switch_state` datapoint (would drive a proper "pre-heating active"
  status sensor, matching `danfoss_ally`'s `pre_heating` binary sensor)
  has not been identified yet - Pre-heat is only exposed as a plain
  on/off switch (dp 1) for now.

## Credits

`climate.py` and `entity.py`'s shared-entity pattern are adapted from
[`mtrab/danfoss_ally`](https://github.com/mtrab/danfoss_ally) (GPLv3),
which controls the same hardware over Danfoss's cloud API. This project
is a from-scratch reimplementation of the coordinator/write layer for the
local Tuya protocol - the raw DP numbers, the write order for Manual
mode, and every other local-protocol-specific detail were reverse
engineered independently (see `docs/`), since `mtrab/danfoss_ally` never
deals with raw datapoints at all (it uses Danfoss's named-field cloud
API).

## License

GPLv3, inherited from `mtrab/danfoss_ally`.

## A personal note

For a couple of years I kept rerouting requests to the Danfoss API through VPNs and
proxies, and in the end I just got tired of it. I could not care less about
their decision to geo-restrict the API - it is about the dumbest restriction
imaginable. What disgusts me is something else - that they find it normal to
take away from people what they paid for, people who chose their heating system
precisely because it had an open API. My heating should not depend on whoever
decides to play the big boss in this world. And yes, I am from Russia. And yes,
that is exactly the problem. And yes, I feel sick about what is happening, and
ashamed of it too, as if part of it were on me.
