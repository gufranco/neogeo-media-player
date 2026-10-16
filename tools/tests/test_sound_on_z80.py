from __future__ import annotations

import os
from pathlib import Path

import pytest
from z80 import Cpu, Memory

ROOT = Path(__file__).resolve().parents[2]
DRIVER = ROOT / "build" / "rom" / "m1.m1"
ROM_REQUIRED_ENV = "NEOGEOMEDIA_ROM_REQUIRED"
ADDRESS_SPACE = 0x10000
STEP_LIMIT = 200_000
SOUND_CODE = 0x00
YM_ADDR = 0x04
YM_DATA = 0x05
SOUND_REPLY = 0x0C
YM_IDLE = 0x00
CMD_SHIFT_PAGE = 0x10
CMD_PLAY = 0x50
CMD_STOP = 0x60
REG_CONTROL = 0x10
REG_PAN = 0x11
REG_START_LO = 0x12
REG_START_HI = 0x13
REG_LEVEL = 0x1B
REG_SSG_MIXER = 0x07
CONTROL_RESET = 0x01
CONTROL_PLAY_LOOPED = 0xB0
PAN_BOTH = 0xC0
LEVEL_MAX = 0xFF
SSG_ALL_OFF = 0x3F


class Ports:
    def __init__(self) -> None:
        self.command = 0
        self.address = 0
        self.registers: list[tuple[int, int]] = []
        self.replies: list[int] = []

    def read(self, address: int) -> int:
        if address & 0xFF == SOUND_CODE:
            return self.command
        return YM_IDLE

    def write(self, address: int, value: int) -> None:
        port = address & 0xFF
        if port == YM_ADDR:
            self.address = value
        elif port == YM_DATA:
            self.registers.append((self.address, value))
        elif port == SOUND_REPLY:
            self.replies.append(value)


@pytest.fixture
def driver():
    if not DRIVER.is_file():
        if os.environ.get(ROM_REQUIRED_ENV) == "1":
            pytest.fail(f"{DRIVER.name} is missing and {ROM_REQUIRED_ENV}=1")
        pytest.skip("run `make rom` first; this runs the cartridge's own sound driver")
    image = DRIVER.read_bytes()[:ADDRESS_SPACE].ljust(ADDRESS_SPACE, b"\x00")
    ports = Ports()
    cpu = Cpu("z80", Memory(image=image), ports=ports)
    cpu.reset()
    settle(cpu)
    return cpu, ports


def settle(cpu: Cpu) -> None:
    for _ in range(STEP_LIMIT):
        if cpu.halted:
            return
        cpu.step()
    pytest.fail(f"the driver did not reach its idle halt within {STEP_LIMIT} steps")


def send(cpu: Cpu, ports: Ports, *codes: int) -> None:
    for code in codes:
        ports.command = code
        cpu.nmi()
        settle(cpu)


class TestBoot:
    def test_the_driver_silences_the_ssg_and_sets_up_adpcm_b(self, driver):
        # Arrange
        _, ports = driver

        # Act
        written = dict(ports.registers)

        # Assert
        assert (written[REG_SSG_MIXER], written[REG_PAN], written[REG_LEVEL]) == (
            SSG_ALL_OFF,
            PAN_BOTH,
            LEVEL_MAX,
        )


class TestCommands:
    def test_four_nibbles_then_play_start_at_that_page(self, driver):
        # Arrange
        cpu, ports = driver
        ports.registers = []

        # Act
        send(cpu, ports, *(CMD_SHIFT_PAGE | nibble for nibble in (1, 2, 3, 4)), CMD_PLAY)

        # Assert
        written = ports.registers
        assert (written[0], written[1], written[2], written[-1]) == (
            (REG_CONTROL, CONTROL_RESET),
            (REG_START_LO, 0x34),
            (REG_START_HI, 0x12),
            (REG_CONTROL, CONTROL_PLAY_LOOPED),
        )

    def test_stop_resets_the_adpcm_b_channel(self, driver):
        # Arrange
        cpu, ports = driver
        ports.registers = []

        # Act
        send(cpu, ports, CMD_STOP)

        # Assert
        assert ports.registers == [(REG_CONTROL, CONTROL_RESET)]

    def test_every_command_is_acknowledged_with_a_rising_count(self, driver):
        # Arrange
        cpu, ports = driver
        ports.replies = []

        # Act
        send(cpu, ports, CMD_STOP, CMD_STOP, CMD_STOP)

        # Assert
        assert ports.replies == [1, 2, 3]

    def test_an_unknown_command_is_acknowledged_and_writes_nothing(self, driver):
        # Arrange
        cpu, ports = driver
        ports.registers = []

        # Act
        send(cpu, ports, 0x70)

        # Assert
        assert ports.registers == []
