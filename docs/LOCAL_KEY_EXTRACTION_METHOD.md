# Способ извлечения Tuya local_key из приложения Danfoss Ally

Рабочий метод, подтверждённый 2026-08-04: получен `local_key` шлюза Danfoss Ally
Gateway без реверс-инжиниринга нативного крипто-кода и без краша на x86-эмуляторе.

## Итог (что уже добыто)

```
device_id: <GATEWAY_DEVICE_ID>   (Danfoss Ally Gateway)
local_key: <GATEWAY_LOCAL_KEY>          (16 символов, ASCII, как есть — не hex)
```

Остальные 6 Icon2 RT термостатов и Icon2 Controller — **отдельных local_key не
имеют и не требуют**. Они Zigbee-суб-устройства под гейтвеем
(`"communicationNode":"<GATEWAY_DEVICE_ID>"`, `"devAttribute":2048` в их
JSON-записи) и адресуются локально через `tuya_local`/LocalTuya как sub-devices
гейтвея — по его же `local_key` + их `nodeId` (= `device_cid`). Один ключ на
всю систему.

### Полная таблица device_cid (2026-08-04, извлечено из того же дампа памяти)

Все `nodeId` нашлись в уже снятом дампе `mem_scan_out2.txt` — открывать
карточку каждого устройства заново не понадобилось, топология (`deviceTopo`)
приходит с обычным списком устройств, в отличие от `localKey`, который
подгружается лениво только при открытии конкретной панели.

**Нумерация RT в приложении НЕ совпадает с суффиксом nodeId** — это просто
порядок Zigbee-сопряжения, а не привязка к номеру термостата. Брать строго
из таблицы.

| Устройство | device_id | device_cid (nodeId) |
|---|---|---|
| Ally Gateway | `<GATEWAY_DEVICE_ID>` | — (не добавлять отдельным устройством, у него нет DPS) |
| Icon2 Controller | `<ICON2_CONTROLLER_DEVICE_ID>` | `<ZIGBEE_BASE_NODE_ID>` |
| Icon2 RT 1 | `<RT1_DEVICE_ID>` | `<ZIGBEE_BASE_NODE_ID>-01` ✅ проверен рабочим DPS-запросом |
| Icon2 RT 2 | `<RT2_DEVICE_ID>` | `<ZIGBEE_BASE_NODE_ID>-02` |
| Icon2 RT 6 | `<RT6_DEVICE_ID>` | `<ZIGBEE_BASE_NODE_ID>-03` |
| Icon2 RT 3 | `<RT3_DEVICE_ID>` | `<ZIGBEE_BASE_NODE_ID>-04` |
| Icon2 RT 4 | `<RT4_DEVICE_ID>` | `<ZIGBEE_BASE_NODE_ID>-05` |
| Icon2 RT 5 | `<RT5_DEVICE_ID>` | `<ZIGBEE_BASE_NODE_ID>-06` |

Для всех записей: `host = <GATEWAY_LAN_IP>`, `local_key = <GATEWAY_LOCAL_KEY>`,
`protocol_version = 3.5`.

## Добавление в Home Assistant через `tuya_local`

Если уже установлена интеграция **Tuya Local** (домен `tuya_local`,
проект make-all/tuya-local — не путать с LocalTuya rospogrigio) — её форма
ручного добавления (`setup_mode: manual`) содержит поле `device_cid` из
коробки — проверено напрямую через `config_entries/flow` REST API на живой
инсталляции. Для каждого суб-устройства из таблицы выше: `device_id` + `host`
+ `local_key` + `protocol_version=3.5` + свой `device_cid`. Гейтвей отдельным
устройством не добавлять.

## Проверено end-to-end (2026-08-04, tinytuya)

Ключ подтверждён дважды, независимо:

1. **Криптографически** — на протоколе 3.5 сессионный handshake (согласование
   session key через зашифрованный `local_key`-ом обмен nonce) успешно
   завершается ("Session key negotiate success!"). Это возможно только с
   правильным ключом — если бы ключ был неверный, расшифровка nonce на шаге 2
   дала бы мусор и handshake сразу бы упал.
2. **Функционально** — реальный live-статус получен с RT1
   (`<RT1_DEVICE_ID>`) через шлюз:
   ```
   {"1":true,"3":"Heat","18":350,"24":265,"27":40,"30":true,"34":65,"45":0,
    "101":268,"103":"0x8041","106":640,"108":180,"110":50,"111":"Manual",
    "114":50,"116":350,"117":"Comfort","120":50,"123":false,"124":true,
    "126":true,"135":0,"137":false,"139":"hide","140":"Inactive","141":"hot"}
   ```
   `"24":265` (26.5°C) и `"34":65` (батарея 65%) один в один совпали с тем,
   что показывало приложение/HA в этот момент.

### Важно: сам шлюз не отвечает на простой status-запрос

Прямой `status()` к `<GATEWAY_DEVICE_ID>` без `cid` даёт
`{'Error': 'Invalid JSON Response from Device', 'Err': '900', ...}` —
**это не ошибка ключа**, сессия каждый раз успешно устанавливается. У самого
гейтвея нет собственных DPS (`"dps":{}` в его записи, `productStandardConfig`
с пустым `statusSchemaList`) — это чистый мост. Запрашивать нужно
суб-устройство, передавая его `cid` = `nodeId` из топологии
(`"deviceTopo":{"nodeId":"...","parentDevId":"<GATEWAY_DEVICE_ID>"}` в
JSON записи каждого RT/Controller):

```python
import tinytuya
gw = tinytuya.Device(GATEWAY_ID, IP, LOCAL_KEY, version=3.5, persist=True)
sub = tinytuya.Device(RT_DEVICE_ID, IP, LOCAL_KEY, version=3.5,
                       cid=RT_NODE_ID, parent=gw)
sub.status()  # -> {'dps': {...}, 'cid': RT_NODE_ID, ...}
```

Для RT1 `nodeId` оказался `<ZIGBEE_BASE_NODE_ID>-01` (найден в том же дампе
памяти, что и `localKey`, в поле `deviceTopo`). `nodeId` остальных RT нужно
доставать так же — через дамп памяти после открытия их карточек, либо
опытным путём (похоже на `<mac_гейтвея>-0N`, но это не проверено для
RT2–RT6, нужно смотреть каждый конкретно).

Тестовые скрипты в этой же папке: `test_local_key.py` (первый неудачный
заход с bare status), `test_local_key2.py` (диагностика с ручным handshake),
`test_local_key3.py` (рабочий вариант с `cid`).

**Вывод для LocalTuya-интеграции в HA:** гейтвей нужно добавлять в режиме
"Zigbee-шлюз с суб-устройствами" (сама HA-интеграция LocalTuya это умеет —
там при добавлении устройства есть выбор "gateway"/sub-device с полем cid),
а не как обычное одиночное устройство.

## Почему предыдущий подход (Frida-хук на нативную AES-функцию) не понадобился

Раньше считалось, что `local_key` появляется только в момент активной отправки
команды устройству (нативный вызов `mbedtls_aes_setkey_enc/dec` в
`libmbedcrypto.so`), а отправка команды стабильно крашила приложение на
x86-эмуляторе через `libhoudini.so` (ARM→x86 транслятор, потому что APK несёт
только `arm64-v8a`/`armeabi-v7a` нативные библиотеки).

На деле `local_key` подгружается в JS/JSON-модель устройства **уже при
открытии карточки устройства в приложении** (простой просмотр, без нажатия
кнопок управления) — то есть краш-путь вообще не нужен.

## Пошаговый метод

### Предпосылки
- Рутованный Android (в этом случае — LDPlayer x86-эмулятор, но подойдёт и
  реальный телефон) с установленным и залогиненным приложением
  `com.danfoss.ally`.
- `adb` с root-доступом (`adb shell su -c ...` работает).
- `frida-server` запущен на устройстве (бинарник лежал в
  `/data/local/tmp/frida-server`, поднимается как `su -c '/data/local/tmp/frida-server &'`).
- На хосте: `pip install frida` (использовалась версия `frida==17.16.4`,
  клиент должен примерно совпадать по мажорной версии с `frida-server`).

### Шаги
1. Запустить приложение и убедиться, что аккаунт залогинен и список
   устройств загружен и показывает живые данные (не просто список, а с
   актуальными температурами и т.п.):
   ```
   adb shell am start -n com.danfoss.ally/com.smart.ThingSplashActivity
   ```
2. **Открыть карточку конкретного устройства** (тап по плитке в списке) —
   это и есть триггер подгрузки его `localKey` в память. Ничего внутри
   карточки нажимать не нужно — не менять температуру, не дёргать
   переключатели. Для гейтвея хватило просто открыть его панель
   ("Устройства в сети: 7").
3. Найти PID процесса:
   ```
   adb shell su -c 'ps -A' | grep danfoss
   ```
   (нужен процесс с именем `Ally`/`com.danfoss.ally`, НЕ `:monitor` — это
   отдельный дочерний процесс без нужных данных).
4. Подключиться Frida по PID (не по имени пакета — process name у Frida
   оказался просто `Ally`, а не `com.danfoss.ally`) и просканировать всю
   память процесса на предмет байт-строки нужного `device_id`. Вокруг
   каждого совпадения выгрузить ~3KB окружающего текста — там лежит целиком
   JSON-запись устройства из локального кэша Tuya SDK, включая поле
   `"localKey":"..."`.
5. Прогрепать вывод по `"localKey":"` — если рядом с нужным `devId` значение
   непустое, это и есть искомый ключ.

Рабочий скрипт (`mem_scan.py`, лежит в этой же папке) делает шаги 3–5
автоматически: подключается к процессу `Ally` по PID через
`frida.get_usb_device().attach(pid)`, инжектит JS-скрипт с
`Memory.scanSync` по всем `r--`/`rw-` регионам памяти, для каждого
совпадения возвращает ASCII-дамп окрестности через `ptr.readByteArray(len)`
(в новых версиях Frida это метод указателя, а не `Memory.readByteArray()` —
последнее устарело и падает с `TypeError: not a function`).

### Особенности/грабли
- Процесс приложения может неожиданно падать между запусками скрипта
  (`frida.NotSupportedError: unable to write to process memory: No such
  process` при живом PID в `ps`) — просто перезапустить сканирование ещё раз,
  обычно проходит со второй попытки.
- MMKV-хранилища приложения на диске (`/data/data/com.danfoss.ally/files/thingmmkv/`)
  зашифрованы (энтропия ~8 бит/байт) — пассивное чтение диска без запуска
  приложения `local_key` не даст, ключ существует только в расшифрованном
  виде в оперативной памяти работающего процесса.
- `RKStorage` (React Native AsyncStorage SQLite) и `shared_prefs/*.xml` —
  пустые/нерелевантные, там `local_key` не хранится вообще.

## Проверка результата

Ключ ещё не был протестирован через LocalTuya — следующий шаг: добавить в
Home Assistant интеграцию LocalTuya на IP гейтвея `<GATEWAY_LAN_IP>`, протокол
`3.5`, `device_id = <GATEWAY_DEVICE_ID>`, `local_key` как выше, и
проверить, что приходит реальный статус устройства.

См. также память `danfoss-ally-tuya-local-key` и бриф
`REVERSE_ENGINEERING_BRIEF.md` в этой же папке.
