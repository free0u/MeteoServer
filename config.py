import json
import os
from dataclasses import dataclass

CONFIG_PATH = "config.json"


class Config:
    def __init__(self):
        d = self.read_config()

        y = d["common"]
        common_config = CommonConfig(**y)
        self.common = common_config
        self.common.routes = CommonRoutesConfig(**common_config.routes)

        y = d["healthchecks"]
        self.healthchecks = HealthchecksConfig(**y)

        self.simple_auth = SimpleAuth(**d["simple_auth"])
        self.influxdb = InfluxdbConfig(**d["influxdb"])
        self.narodmon = NarodmonConfig(**d["narodmon"])
        self.thingspeak = ThingspeakConfig(
            columbus=ThingspeakDeviceConfig(**d["thingspeak"]["columbus"]),
            opus=ThingspeakDeviceConfig(**d["thingspeak"]["opus"]),
            wave=ThingspeakDeviceConfig(**d["thingspeak"]["wave"]),
            chel=ThingspeakDeviceConfig(**d["thingspeak"]["chel"]),
            moxovich=ThingspeakDeviceConfig(**d["thingspeak"]["moxovich"]),
            moxovich_second=ThingspeakDeviceConfig(
                **d["thingspeak"]["moxovich_second"]
            ),
        )

    @staticmethod
    def read_config():
        path = os.path.expanduser(CONFIG_PATH)
        with open(path, "r") as f:
            config = json.load(f)
            return config

    def __str__(self):
        return json.dumps(self, default=lambda x: x.__dict__, indent=2, sort_keys=True)


@dataclass
class CommonRoutesConfig:
    send_data: str
    update_device: str
    root: str
    heartbeat_handle: str
    sensor_data: str
    log: str


@dataclass
class CommonConfig:
    api_key: str
    api_url: str
    routes: CommonRoutesConfig


@dataclass
class HealthchecksConfig:
    device_arctic: str
    device_chel: str
    device_chel_osmos: str
    device_chel_flaner: str
    device_dimple: str
    device_columbus: str
    device_dino: str
    device_opus: str
    device_sunny: str
    device_wave: str
    device_moxovich: str
    device_moxovich_second: str


@dataclass
class ThingspeakDeviceConfig:
    id: str
    token: str


@dataclass
class ThingspeakConfig:
    columbus: ThingspeakDeviceConfig
    opus: ThingspeakDeviceConfig
    wave: ThingspeakDeviceConfig
    chel: ThingspeakDeviceConfig
    moxovich: ThingspeakDeviceConfig
    moxovich_second: ThingspeakDeviceConfig


@dataclass
class InfluxdbConfig:
    url: str
    token: str


@dataclass
class NarodmonConfig:
    chel_mac: str
    columbus_mac: str
    moxovich_mac: str


@dataclass
class SimpleAuth:
    header_key: str
    header_value: str


def main():
    config = Config()
    print(str(config))


if __name__ == "__main__":
    main()
