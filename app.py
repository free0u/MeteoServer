import json
import re
import time
from datetime import datetime, timedelta
from functools import reduce

import requests
import urllib.parse
from flask import Flask
from flask import Response
from flask import abort
from flask import jsonify, send_file
from flask import request
from config import Config

app = Flask(__name__)

updateUrlBase = "https://api.thingspeak.com/update?"

config = Config()


class Kalman:
    def __init__(self, err_measure, q):
        self._err_measure = err_measure
        self._err_estimate = err_measure
        self._q = q
        self.first_measure = True

    def get(self, mea):
        if self.first_measure:
            self.first_measure = False
            self._last_estimate = mea
            return mea

        self._kalman_gain = self._err_estimate / (
            self._err_estimate + self._err_measure
        )
        self._current_estimate = self._last_estimate + self._kalman_gain * (
            mea - self._last_estimate
        )
        self._err_estimate = (1.0 - self._kalman_gain) * self._err_estimate + abs(
            self._last_estimate - self._current_estimate
        ) * self._q
        self._last_estimate = self._current_estimate

        return self._current_estimate


class KalmanId:
    def __init__(self):
        pass

    def get(self, mea):
        return mea


kalman_temp_out = Kalman(0.01, 0.01)

kalman_temp_in = Kalman(0.02, 0.01)
kalman_pressure = Kalman(0.03, 0.01)
kalman_hum_in = Kalman(0.02, 0.01)

# temp_in;temp_out;hum_out;hum_in;pressure;co2;co2uart;uptime
fields = {}
fields["temp_out"] = "field1"
# fields['temp_in_bak'] = 'field2'
fields["temp_in"] = "field3"
# fields['hum_in'] = 'field4'
fields["co2"] = "field5"
# fields['pressure'] = 'field6'
# fields['uptime'] = 'field7'
# fields['co2uart'] = 'field8'
api_key = "REMOVED"


def pairParam(field, value):
    return "&" + str(field) + "=" + str(value)


def moscowTimeString():
    utc = datetime.utcnow()
    fmt = "%Y-%m-%d %H:%M:%S"
    t = utc + timedelta(hours=3)
    return t.strftime(fmt)


def secondsSinceMid():
    now = datetime.now()
    seconds_since_midnight = (
        now - now.replace(hour=0, minute=0, second=0, microsecond=0)
    ).total_seconds()
    return seconds_since_midnight


@app.route(config.common.routes.root)
def hello():
    # return jsonify(res)
    return "hello"


# healthchecks.io
healthchecks_map = {}

# esp devices
healthchecks_map["device_arctic"] = config.healthchecks.device_arctic

healthchecks_map["device_chel"] = config.healthchecks.device_chel
healthchecks_map["device_chel_osmos"] = config.healthchecks.device_chel_osmos
healthchecks_map["device_chel_flaner"] = config.healthchecks.device_chel_flaner
healthchecks_map["device_dimple"] = config.healthchecks.device_dimple

healthchecks_map["device_columbus"] = config.healthchecks.device_columbus
healthchecks_map["device_dino"] = config.healthchecks.device_dino
healthchecks_map["device_opus"] = config.healthchecks.device_opus
healthchecks_map["device_sunny"] = config.healthchecks.device_sunny
healthchecks_map["device_wave"] = config.healthchecks.device_wave

healthchecks_map["device_moxovich"] = config.healthchecks.device_moxovich
healthchecks_map["device_moxovich_second"] = config.healthchecks.device_moxovich_second


def sendHeartbeat(service):
    if not service:
        return "error"
    app.logger.info("[sendHeartbeat]: {}".format(service))

    url = config.common.api_url + config.common.routes.send_data + "?tag=" + service
    headers = {"Sensors-Names": "heartbeat"}

    data = str(int(time.time()))
    data += ";1;0"

    ret = {}
    ret["url"] = url
    ret["headers"] = headers
    ret["data"] = data

    r = requests.post(url, headers=headers, data=data)

    # send to healthchecks.io
    if service in healthchecks_map:
        requests.get(
            "https://hc-ping.com/{}".format(healthchecks_map[service]), timeout=5
        )

    return jsonify(ret)


@app.route("/heartbeat")
def heartbeat():
    if config.simple_auth.header_key not in request.headers:
        return "error"
    if (
        request.headers[config.simple_auth.header_key]
        != config.simple_auth.header_value
    ):
        return "error"

    service = request.args.get("service")

    return sendHeartbeat(service)


def convert_to_thingspeak_format(data):
    if not data["name"] in fields:
        return {}
    return {"created_at": data["ts"], fields[data["name"]]: data["value"]}


# kalman_hum_in = Kalman(0.02, 0.01)
kalmans = {}
kalmans["opus"] = {}
kalmans["wave"] = {}
kalmans["columbus"] = {}
kalmans["chel"] = {}
kalmans["macbook2017"] = {}
kalmans["dino"] = {}
kalmans["arctic"] = {}
kalmans["moxovich"] = {}
kalmans["chel_flaner"] = {}
kalmans["dimple"] = {}

kalmans["wave"]["temp_in"] = Kalman(0.01, 0.01)
kalmans["wave"]["hum_in"] = Kalman(0.01, 0.01)
kalmans["wave"]["co2"] = Kalman(0.01, 0.01)

kalmans["opus"]["co2"] = Kalman(0.01, 0.01)
kalmans["opus"]["temp_in"] = Kalman(0.01, 0.01)
kalmans["opus"]["temp_out"] = Kalman(0.01, 0.01)
kalmans["opus"]["hum_in"] = Kalman(0.01, 0.01)

kalmans["dino"]["co2"] = Kalman(0.01, 0.01)
kalmans["dino"]["temp_in"] = Kalman(0.01, 0.01)
kalmans["dino"]["hum_in"] = Kalman(0.01, 0.01)

kalmans["columbus"]["temp_out"] = Kalman(0.1, 0.01)
# 0: 0.01, 0.01
# 1: 0.1, 0.01


kalmans["columbus"]["temp_in"] = Kalman(0.01, 0.01)
kalmans["columbus"]["hum_out"] = Kalman(0.01, 0.01)
kalmans["columbus"]["hum_in"] = Kalman(0.01, 0.01)

kalmans["chel"]["temp_out"] = Kalman(0.01, 0.01)
kalmans["chel"]["temp_in"] = Kalman(0.01, 0.01)
kalmans["chel"]["hum_in"] = Kalman(0.01, 0.01)
kalmans["chel"]["co2"] = Kalman(0.01, 0.01)

kalmans["moxovich"]["temp_out"] = Kalman(0.01, 0.01)

kalmans["chel_flaner"]["temp_in"] = Kalman(0.1, 0.01)
kalmans["chel_flaner"]["hum_in"] = Kalman(0.1, 0.01)

kalmans["arctic"]["temp_out"] = Kalman(0.01, 0.01)
kalmans["arctic"]["temp_in"] = Kalman(0.01, 0.01)

kalmans["macbook2017"]["temp_in"] = Kalman(0.1, 0.01)


def convert_to_influx(data, tag):
    global kalmans
    kalman = KalmanId()

    nm = data["name"]

    if tag in kalmans:
        if nm in kalmans[tag]:
            kalman = kalmans[tag][nm]

    nv = kalman.get(float(data["value"]))
    ret = (
        data["name"]
        + ",device="
        + tag
        + " value="
        + str(data["value"])
        + ",kalman="
        + str(nv)
        + " "
        + str(data["ts"])
    )

    if tag == "pg":
        name = "pg"
        device = "wave"
        value_name = data["name"]
        alue = float(data["value"])
        ret = (
            name
            + ",device="
            + device
            + " "
            + value_name
            + "="
            + data["value"]
            + " "
            + str(data["ts"])
        )

    # with open("static/log.txt", "a") as f:
    #     f.write(str(datetime.now()))
    #     f.write("\n")
    #     f.write("ret: \n")
    #     f.write(ret)
    #     f.write("\n\n\n")

    return ret

    # return data['name'] + ",device=" + tag + " value=" + str(data['value']) + " " + str(data['ts'])


sensors_cache = []
thingspeak_sent_ts = 0
thingspeak_sent_mox_ts = 0

ts_tags = ["chel", "columbus", "opus", "wave"]
ts_tags_ind = 0

device_heartbeats = dict()


def get_alive_devices(secs=3):
    ts = int(time.time())
    ret = []
    for tag in device_heartbeats:
        if ts - device_heartbeats[tag] < secs:
            ret.append(tag)
    return ret
    pass


narodmon_macs = {}
narodmon_macs["chel"] = config.narodmon.chel_mac
narodmon_macs["moxovich"] = config.narodmon.moxovich_mac
narodmon_macs["columbus"] = config.narodmon.columbus_mac

# by device
narodmon_last_send = {}

narodmon_last_send_common = None


def send_to_narodmon(data, tag):
    ts = int(time.time())  # secs

    global narodmon_last_send_common
    # for skipping first time after reset
    if narodmon_last_send_common is None:
        narodmon_last_send_common = ts

    if ts - narodmon_last_send_common < 1 * 60 + 5:  # 1 min
        app.logger.info(
            "[send_to_narodmon]: skip by time for common send (IP 1 min). diff: {} ".format(
                ts - narodmon_last_send_common
            )
        )
        return

    app.logger.info("[send_to_narodmon]: try for: {}".format(tag))

    global narodmon_macs
    global narodmon_last_send

    if not tag in narodmon_macs:
        return
    mac = narodmon_macs[tag]

    if not tag in narodmon_last_send:
        narodmon_last_send[tag] = ts

    if ts - narodmon_last_send[tag] < 5 * 60 + 2:  # 5 min
        app.logger.info(
            "[send_to_narodmon]: skip by time for (device 5 min): {}".format(tag)
        )
        return

    narodmon_last_send[tag] = ts
    narodmon_last_send_common = ts

    app.logger.info("[send_to_narodmon]: sending for: {}".format(tag))

    data = list(filter(lambda x: "temp_out" == x["name"], data))

    if len(data) > 0:
        data = data[-1]

    device = {}
    device["mac"] = mac

    device["sensors"] = [{"id": "temp_out", "value": data["value"]}]

    body = {}
    body["devices"] = [device]

    app.logger.debug("[send_to_narodmon]: data: {}".format(str(data)))
    app.logger.debug("[send_to_narodmon]: body: {}".format(str(body)))

    try:
        r = requests.post("https://narodmon.ru/json", json=body)
        app.logger.info("[send_to_narodmon]: result: {}".format(str(r.text)))
        pass
    except Exception as e:
        return e


mox_ts_send = {}
mox_ts_send["moxovich"] = 0
mox_ts_send["moxovich_second"] = 0
mox_ts_send_common = 0


def send_to_thingspeak(data, token, channel, tag):
    app.logger.info("[send_to_thingspeak]: try for: " + str(tag))
    app.logger.info(
        "[send_to_thingspeak]: channel: " + str(channel) + " data: " + str(data)
    )
    global sensors_cache
    global thingspeak_sent_ts
    global thingspeak_sent_mox_ts
    global ts_tags
    global ts_tags_ind
    global device_heartbeats
    # sensors_cache.extend(data)
    ts = int(time.time())

    device_heartbeats[tag] = ts

    if (
        tag != "moxovich" and tag != "moxovich_second"
    ):  # always send moxovich because separate channel
        alive_devices = get_alive_devices(30)
        if not ts_tags[ts_tags_ind] in alive_devices:
            app.logger.info(
                "[send_to_thingspeak]: found dead device: {}, alive: {}".format(
                    ts_tags[ts_tags_ind], str(alive_devices)
                )
            )
            ts_tags_ind = (ts_tags_ind + 1) % len(ts_tags)

        app.logger.info(
            "[send_to_thingspeak]: alive devices: {}".format(str(alive_devices))
        )

        if ts - thingspeak_sent_ts < 25:
            app.logger.info(
                "[send_to_thingspeak]: skip by time for: {} (wait for {})".format(
                    str(tag), ts_tags[ts_tags_ind]
                )
            )

            return 0

        if tag != ts_tags[ts_tags_ind]:
            app.logger.info(
                "[send_to_thingspeak]: skip by order for: {} (wait for {})".format(
                    str(tag), ts_tags[ts_tags_ind]
                )
            )
            return 0

        ts_tags_ind = (ts_tags_ind + 1) % len(ts_tags)
    else:  # моховички оба
        app.logger.info("[send_to_thingspeak] mox: try for {}".format(str(tag)))
        if ts - thingspeak_sent_mox_ts < 25:
            app.logger.info(
                "[send_to_thingspeak] mox: skip by time common for: {}".format(str(tag))
            )
            return 0
        if ts - mox_ts_send[tag] < 65:  # 1 min
            app.logger.info(
                "[send_to_thingspeak] mox: skip by time per device for: {}".format(
                    str(tag)
                )
            )
            return 0
        thingspeak_sent_mox_ts = ts
        mox_ts_send[tag] = ts
        app.logger.info(
            "[send_to_thingspeak] mox: beginning to send for {}".format(str(tag))
        )
        pass
    # sensors_cache = data

    # A = sensors_cache[:300]
    # B = sensors_cache[300:]

    body = {}
    body["write_api_key"] = token
    # body['updates'] = A
    body["updates"] = data[:30]

    try:

        r = requests.post(
            "http://api.thingspeak.com/channels/" + channel + "/bulk_update.json",
            json=body,
        )
        resp = r.json()
        if "success" in resp and resp["success"]:
            # sensors_cache = B
            app.logger.info(
                "[send_to_thingspeak]: success: channel:"
                + str(channel)
                + " "
                + str(resp)
                + " for "
                + tag
                + " body: "
                + str(body)
            )

        else:
            app.logger.info("[send_to_thingspeak]: error for " + tag + " " + str(resp))
        if tag != "moxovich":  # always send moxovich because separate channel
            thingspeak_sent_ts = ts
    except Exception as e:
        return e

    return len(sensors_cache)


def updateDeviceImpl(deviceName, deviceVersion):
    app.logger.info("[deviceUpdate] updateDeviceImpl")

    devs_list = []
    with open("updateDevices.txt", "r") as f:
        devs_list = f.readlines()
        devs_list = list(map(lambda x: x.strip(), devs_list))

    app.logger.info("[deviceUpdate] devicesToUpdate: " + str(devs_list))

    devsWithTargetVersion = {}
    for dev in devs_list:
        spl = dev.split(":")
        devsWithTargetVersion[spl[1]] = int(spl[0])

    app.logger.info("[deviceUpdate] devicesToUpdate map: " + str(devsWithTargetVersion))

    lines = []
    with open("version.txt", "r") as f:
        lines = f.readlines()
    currentVersion = lines[0]
    app.logger.info("[deviceUpdate] And we have version %s", currentVersion)

    if deviceName in devsWithTargetVersion:
        binVersion = int(currentVersion)
        deviceCurrentVersion = int(deviceVersion)
        deviceTargetVersion = devsWithTargetVersion[deviceName]
        if (
            deviceCurrentVersion < deviceTargetVersion
            and deviceTargetVersion == binVersion
        ):
            app.logger.info("[deviceUpdate] Need update")
            return send_file(
                "firmware.bin",
                attachment_filename="firmware.bin",
                as_attachment=True,
                mimetype="application/octet-stream",
            )
        else:
            app.logger.info("[deviceUpdate] Update not needed")

    return Response("No update", status=304, mimetype="application/text")


@app.route(config.common.routes.update_device, methods=["GET"])
def update_device():
    # wrtest
    # abort(500)

    deviceName = request.args.get("device")
    deviceVersion = request.args.get("version")

    if deviceName is None:
        abort(500)
    if deviceVersion is None:
        abort(500)

    if deviceName in deviceNames:
        sendHeartbeat("device_{}".format(deviceName))

    app.logger.info(
        "[deviceUpdate] Requested update for device %s with version %s",
        deviceName,
        deviceVersion,
    )
    return updateDeviceImpl(deviceName, deviceVersion)

    return Response("No update", status=304, mimetype="application/text")


deviceNames = []
deviceNames.append("wave")
deviceNames.append("columbus")
deviceNames.append("opus")
deviceNames.append("sunny")
deviceNames.append("chel")
deviceNames.append("dino")
deviceNames.append("arctic")
deviceNames.append("moxovich")
deviceNames.append("moxovich_second")
deviceNames.append("dimple")
deviceNames.append("chel_flaner")
deviceNames.append("chel_osmos")

heartTags = []
heartTags.append("device_arctic")
heartTags.append("device_chel")
heartTags.append("device_columbus")
heartTags.append("device_opus")
heartTags.append("device_wave")
heartTags.append("device_dino")
heartTags.append("device_sunny")
heartTags.append("device_moxovich")
heartTags.append("device_chel_flaner")
heartTags.append("device_dimple")
heartTags.append("sync_notes")
heartTags.append("sync_vacuum")
heartTags.append("trello_scripts")
heartTags.append("ynab_sync_reconcile")
heartTags.append("ynab_sync_tinkoff")
heartTags.append("backup_rasp")
heartTags.append("check_ci")


@app.route(config.common.routes.heartbeat_handle, methods=["GET"])
def heartbeatHandle():
    offDevices = []
    for dn in deviceNames:
        value = getInternalSensor(dn, "uptime", 10 * 60)
        if value is None:
            offDevices.append(dn)

    ret2 = []
    ind = 1
    for offDevices in offDevices:
        url = (
            config.common.api_url
            + config.common.routes.send_data
            + "?tag="
            + offDevices
        )
        headers = {"Sensors-Names": "uptime"}

        data = str(int(time.time()))
        data += ";" + str(0) + ";"
        data += str(2 * ind)
        ind += 1

        ret = {}
        ret["url"] = url
        ret["headers"] = headers
        ret["data"] = data

        r = requests.post(url, headers=headers, data=data)
        ret2.append((url, headers, data, r.status_code))

    # offDevices = []
    # for dn in heartTags:
    #     value = getInternalSensor(dn, "heartbeat", 20 * 60)
    #     if value is None:
    #         offDevices.append(dn)
    # ind = 1
    # for offDevices in offDevices:

    #     data = str(int(time.time()))
    #     data += ";" + str(0) + ";"
    #     data += str(2 * ind)
    #     ind += 1

    #     ret = {}
    #     ret['url'] = url
    #     ret['headers'] = headers
    #     ret['data'] = data

    #     r = requests.post(url, headers=headers, data=data)
    #     ret2.append((url, headers, data, r.status_code))

    return jsonify(ret2)


@app.route(config.common.routes.sensor_data, methods=["GET"])
def sensorData():
    deviceName = request.args.get("device")
    sensorName = request.args.get("sensor")
    timeout = request.args.get("timeout")

    if deviceName is None:
        abort(500)
    if sensorName is None:
        abort(500)
    if timeout is None:
        timeout = 65

    value = getInternalSensor(deviceName, sensorName, int(timeout))

    if value is None:
        abort(404)

    return jsonify(value)


def getInternalSensor(device, sensor, timeout):
    sec = int(time.time())

    q = (
        "select time,kalman,value from "
        + sensor
        + " where device = '"
        + device
        + "' ORDER BY time DESC limit 1"
    )
    url = config.influxdb.url + "/query?db=meteo&epoch=s&q=" + q

    # app.logger.info("sending to influx")
    headers = {"Authorization": config.influxdb.token}

    app.logger.info("[getInternalSensor]: {}".format(url))
    r = requests.get(url, headers=headers)

    res = r.json()

    # app.logger.info(res)
    # app.logger.info(res['results'])
    # app.logger.info(res['results'][0])
    # app.logger.info(res['results'][0]['series'])
    # app.logger.info(res['results'][0]['series'][0])
    # app.logger.info(res['results'][0]['series'][0]['values'])
    # app.logger.info(res['results'][0]['series'][0]['values'][0])
    # {'results': [{'statement_id': 0, 'series': [{'name': 'heartbeat', 'columns': ['time', 'kalman', 'value'], 'values': [[1626357313, 1, 1]]}]}]}
    v = res["results"][0]["series"][0]["values"][0]
    ts = int(v[0])

    delta = sec - ts

    if delta > timeout:
        return None

    return float(v[1])


@app.route(config.common.routes.log, methods=["POST"])
def log():
    # wrtest
    # abort(500)

    deviceName = request.args.get("device")
    time = request.args.get("time")

    if deviceName is None:
        abort(500)
    if time is None:
        abort(500)

    data = request.data.decode("utf-8")

    # app.logger.info("%s %s", str(len(data)), data)

    with open("static/log2.txt", "a") as f:
        for line in data.split("$"):
            # l = moscowTimeString()
            # l += " name:" + deviceName
            # l += " type:log "
            # l += line
            # l += "\n"

            l = (
                " ".join([moscowTimeString(), "name:" + deviceName, "type:log", line])
                + "\n"
            )

            f.write(l)

    return jsonify("ok")


@app.route(config.common.routes.send_data, methods=["GET", "POST"])
def get_data():
    tag = request.args.get("tag")

    # wrtest
    # abort(500)
    if tag in ["dino", "opus", "columbus"]:
        # abort(500)
        pass

    if tag is None:
        tag = "undef"

    with open("static/log.txt", "a") as f:
        f.write(str(datetime.now()))
        f.write("\n")
        f.write("headers: " + request.url + " \n")
        f.write(str(request.headers["Sensors-Names"]))
        f.write("\n")
        f.write("tag: ")
        f.write("'" + str(tag) + "'")
        f.write("\n")
        d = request.data
        f.write(str(d))
        f.write("\n\n\n")

    sensors_data_raw = request.data.decode("utf-8").split("_")
    sensors_names = request.headers["Sensors-Names"].split(";")
    # app.logger.info("sensors: " + str(sensors_names))
    app.logger.info("items count: " + str(len(sensors_data_raw)))
    sensors_count = len(sensors_names)
    sensors_data = []

    with open("static/log2.txt", "a") as f:
        l = moscowTimeString()
        l += " name:" + tag
        l += " type:sensors_received "
        l += str(request.headers["Sensors-Names"]) + " "
        l += "(" + str(len(sensors_data_raw)) + ") "
        l += "<" + str(request.data)[2:][:20] + "...> "
        l += "url:" + request.url
        l += "\n"
        f.write(l)

    res = {}

    for sensor in sensors_data_raw:
        if sensor:
            values = sensor.split(";")
            ts = int(values[0])
            sensors = []
            for i in range(sensors_count):
                if not values[i * 2 + 1]:
                    continue

                sensor_data = {}
                sensor_data["name"] = sensors_names[i]
                sensor_data["value"] = values[i * 2 + 1]
                sensor_data["ts"] = ts - int(values[i * 2 + 2])
                sensors.append(sensor_data)

            sensors_data.append(sensors)

    sensors_data = reduce(list.__add__, sensors_data)
    ts_data = [
        convert_to_thingspeak_format(e) for e in sensors_data if e["name"] in fields
    ]

    by_ts = {}
    for sensor in sensors_data:
        # ts = sensor['ts']
        ts = sensors_data[0]["ts"]
        if not ts in by_ts:
            by_ts[ts] = {}
        by_ts[ts]["created_at"] = ts
        if sensor["name"] in fields:
            by_ts[ts][fields[sensor["name"]]] = sensor["value"]

    influx_data = [convert_to_influx(e, tag) for e in sensors_data]

    app.logger.info("sending to influx")
    headers = {"Authorization": config.influxdb.token}
    r = requests.post(
        config.influxdb.url + "/write?db=meteo&precision=s",
        data="\n".join(influx_data),
        headers=headers,
    )

    app.logger.info(r.text)
    app.logger.info(r.status_code)
    #
    cnt = 0
    if tag == "chel":
        cnt = send_to_thingspeak(
            list(by_ts.values()),
            config.thingspeak.chel.token,
            config.thingspeak.chel.id,
            "chel",
        )
        send_to_narodmon(sensors_data, "chel")

    if tag == "columbus":
        cnt = send_to_thingspeak(
            list(by_ts.values()),
            config.thingspeak.columbus.token,
            config.thingspeak.columbus.id,
            "columbus",
        )
        send_to_narodmon(sensors_data, "columbus")

    if tag == "opus":
        cnt = send_to_thingspeak(
            list(by_ts.values()),
            config.thingspeak.opus.token,
            config.thingspeak.opus.id,
            "opus",
        )

    if tag == "wave":
        cnt = send_to_thingspeak(
            list(by_ts.values()),
            config.thingspeak.wave.token,
            config.thingspeak.wave.id,
            "wave",
        )

    if tag == "moxovich":
        cnt = send_to_thingspeak(
            list(by_ts.values()),
            config.thingspeak.moxovich.token,
            config.thingspeak.moxovich.id,
            "moxovich",
        )
        send_to_narodmon(sensors_data, "moxovich")
    if tag == "moxovich_second":
        # вместо field3 temp_in переносим в temp_in_bak, котоырй field2 чтобы две бани иметь в одном канале, в разных филдах
        values_list = list(by_ts.values())
        app.logger.info("[send_to_thingspeak] mox before: {}".format(str(values_list)))
        for s in values_list:
            if "field3" in s:
                v = s.pop("field3")
                s["field2"] = v
                app.logger.info("[send_to_thingspeak] mox: {}".format("true"))
        app.logger.info("[send_to_thingspeak] mox after: {}".format(str(values_list)))
        cnt = send_to_thingspeak(
            list(by_ts.values()),
            config.thingspeak.moxovich_second.token,
            config.thingspeak.moxovich_second.id,
            "moxovich_second",
        )
        pass
    return jsonify(cnt)


if __name__ == "__main__":
    app.run(host="0.0.0.0", debug=True)
