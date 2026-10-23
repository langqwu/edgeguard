"""PZEM-004T v3.0 电能计量模块驱动（Modbus-RTU，零第三方依赖）。

用法::

    from src.pzem import PZEM004T
    with PZEM004T("COM3") as meter:
        reading = meter.read()
        print(reading.power, reading.energy)

寄存器（v3.0）::

    0x0000  电压      1 字  0.1 V
    0x0001  电流低字  2 字  0.001 A
    0x0003  功率低字  2 字  0.1 W
    0x0005  电能低字  2 字  1 Wh
    0x0007  频率      1 字  0.1 Hz
    0x0008  功率因数  1 字  0.01

物理接口：模块 5V-TTL 端 -> USB 转 TTL 模块 -> PC（默认 9600 8N1，地址 0x01）。
"""

from __future__ import annotations

import struct
import time
from dataclasses import dataclass
from typing import Optional

try:  # pyserial 是可选的，便于在没有串口的机器上做单元测试
    import serial  # type: ignore
except ImportError:  # pragma: no cover
    serial = None  # type: ignore


REG_VOLTAGE = 0x0000
REG_CURRENT = 0x0001
REG_POWER = 0x0003
REG_ENERGY = 0x0005
REG_FREQUENCY = 0x0007
REG_POWER_FACTOR = 0x0008

REGISTER_COUNT = 10


def _crc16(data: bytes) -> int:
    """Modbus RTU CRC16。"""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc


@dataclass(frozen=True)
class Reading:
    """一次测量结果（已换算为物理单位）。"""

    voltage: float  # V
    current: float  # A
    power: float  # W
    energy: float  # kWh
    frequency: float  # Hz
    power_factor: float  # 0-1

    def as_dict(self) -> dict:
        return {
            "voltage": round(self.voltage, 2),
            "current": round(self.current, 4),
            "power": round(self.power, 2),
            "energy": round(self.energy, 4),
            "frequency": round(self.frequency, 2),
            "power_factor": round(self.power_factor, 3),
        }


class PZEMError(Exception):
    """通信或校验失败。"""


class PZEM004T:
    """PZEM-004T v3.0 客户端。

    :param port: 串口名，例如 ``COM3``（Windows）或 ``/dev/ttyUSB0``（Linux）
    :param address: 模块地址，出厂默认 ``1``
    :param baudrate: 波特率，模块默认 ``9600``
    :param timeout: 串口读超时（秒）
    """

    def __init__(
        self,
        port: str,
        address: int = 1,
        baudrate: int = 9600,
        timeout: float = 1.0,
    ) -> None:
        if serial is None:
            raise ImportError("需要 pyserial：pip install pyserial")
        self.port = port
        self.address = address
        self._serial = serial.Serial(
            port=port,
            baudrate=baudrate,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=timeout,
        )
        time.sleep(0.1)  # 等串口稳定

    # -- 上下文管理 ---------------------------------------------------
    def __enter__(self) -> "PZEM004T":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        if self._serial.is_open:
            self._serial.close()

    # -- 协议 ---------------------------------------------------------
    def _build_request(self) -> bytes:
        frame = struct.pack(
            ">BBHH", self.address, 0x04, REG_VOLTAGE, REGISTER_COUNT
        )
        return frame + struct.pack("<H", _crc16(frame))

    def _transact(self, retries: int = 3) -> bytes:
        """发送读寄存器请求并返回数据段（不含地址/功能码/CRC）。"""
        expected_len = 3 + REGISTER_COUNT * 2 + 2
        last_error: Optional[Exception] = None
        for _ in range(retries):
            self._serial.reset_input_buffer()
            self._serial.write(self._build_request())
            response = self._serial.read(expected_len)
            if len(response) < expected_len:
                last_error = PZEMError(
                    f"响应不完整：收到 {len(response)} 字节，期望 {expected_len}"
                )
                continue
            if _crc16(response[:-2]) != struct.unpack("<H", response[-2:])[0]:
                last_error = PZEMError("CRC 校验失败")
                continue
            if response[1] & 0x80:
                last_error = PZEMError(f"模块返回异常码 0x{response[2]:02X}")
                continue
            return response[3:-2]
        raise last_error or PZEMError("未知通信错误")

    def read(self) -> Reading:
        """读取一组测量值。"""
        payload = self._transact()
        registers = struct.unpack(">10H", payload)

        voltage = registers[0] * 0.1
        current = ((registers[1] << 16) | registers[2]) * 0.001
        power = ((registers[3] << 16) | registers[4]) * 0.1
        energy = ((registers[5] << 16) | registers[6]) * 1.0 / 1000.0
        frequency = registers[7] * 0.1
        power_factor = registers[8] * 0.01

        return Reading(
            voltage=voltage,
            current=current,
            power=power,
            energy=energy,
            frequency=frequency,
            power_factor=power_factor,
        )
