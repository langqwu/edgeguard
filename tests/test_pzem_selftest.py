# -*- coding: utf-8 -*-
"""无硬件自测：用桩串口验证 PZEM 的地址自动探测与读数解码。"""
import sys
import types
import struct

# 构造一个假的 serial 模块（避免依赖真实 pyserial 与硬件）
fake_serial = types.ModuleType("serial")


def _crc16(data: bytes) -> int:
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
    return crc


class FakeSerial:
    def __init__(self, port, baudrate=9600, bytesize=8, parity="N", stopbits=1, timeout=1.0):
        self.port = port
        self.is_open = True
        self._resp = b""
        self.address = 0xF8  # 模拟出厂地址

    def reset_input_buffer(self):
        self._resp = b""

    def write(self, req: bytes):
        addr = req[0]
        reg = (req[2] << 8) | req[3]
        cnt = (req[4] << 8) | req[5]
        if addr != self.address:
            return  # 不应答
        regs = [2201, 0x0000, 1234, 0x0000, 2714, 0x0000, 0x0001, 500, 62, 0][:cnt]
        payload = struct.pack(">" + "H" * len(regs), *regs)
        frame = bytes([addr, 0x04, len(payload)]) + payload
        frame += struct.pack("<H", _crc16(frame))
        self._resp = frame

    def read(self, n):
        d, self._resp = self._resp[:n], self._resp[n:]
        return d

    def close(self):
        self.is_open = False


fake_serial.Serial = FakeSerial
sys.modules["serial"] = fake_serial

sys.path.insert(0, ".")
from src.pzem import PZEM004T, PZEMError  # noqa: E402

meter = PZEM004T("FAKE", address="auto")
print("探测到的地址:", hex(meter.address))
assert meter.address == 0xF8, "应探测到 0xF8"

r = meter.read()
print(f"读数: U={r.voltage}V I={r.current}A P={r.power}W PF={r.power_factor} F={r.frequency}Hz E={r.energy}kWh")
assert abs(r.voltage - 220.1) < 0.01
assert abs(r.current - 1.234) < 0.001
assert abs(r.power - 271.4) < 0.1
assert abs(r.power_factor - 0.62) < 0.01
assert abs(r.frequency - 50.0) < 0.01
meter.close()

# 指定错误地址应报错
try:
    m2 = PZEM004T("FAKE", address=0x05)
    m2.read()
    print("ERROR: 错误地址不应读到数据")
except PZEMError as e:
    print("错误地址按预期报错:", str(e)[:40], "...")

print("SELFTEST OK")
