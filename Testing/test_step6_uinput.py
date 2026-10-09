"""Host tests for the uinput pointer of the Step 6 harness (S6-ADVISOR-GUI-01).

No /dev/uinput, X server, Qt or compositor is used. A fake kernel records the uinput ioctls and
writes, a simulated compositor maps absolute motion onto the X root with a fixed error, and the
host helper runs on real relay files in a thread with a recording device. The assertions cover the
coordinate mapping (including several monitors), the kernel event and ioctl encoding, the bounded
verified move, the refusal of a press at an unverified position, the relay protocol and the helper's
refusals.
"""

from __future__ import annotations

import ctypes
import errno
import json
import os
import struct
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import step6_user_input as ui  # noqa: E402
import step6_uinput_helper as helper  # noqa: E402
import test_step6_user_input as base  # noqa: E402  (FakeXServer and FakeClock)


@pytest.fixture
def clock(monkeypatch):
    fake = base.FakeClock()
    monkeypatch.setattr(ui, "_NOW", fake.now)
    monkeypatch.setattr(ui, "_SLEEP", fake.sleep)
    return fake


# --- coordinate mapping -----------------------------------------------------------------------

def test_absolute_value_spans_the_root_from_edge_to_edge():
    assert ui.absolute_value(0, 1920) == 0
    assert ui.absolute_value(1919, 1920) == ui.UINPUT_ABS_MAX
    assert ui.absolute_value(960, 1920) == round(960 * ui.UINPUT_ABS_MAX / 1919)


def test_multi_monitor_root_is_one_range_so_a_second_monitor_is_reachable():
    # two 1920x1080 monitors side by side: the X root is 3840x1080
    assert ui.absolute_value(2500, 3840) == round(2500 * ui.UINPUT_ABS_MAX / 3839)
    assert ui.absolute_value(540, 1080) == round(540 * ui.UINPUT_ABS_MAX / 1079)


def test_pixels_outside_the_root_are_refused():
    with pytest.raises(ui.UserInputError, match="outside the desktop"):
        ui.absolute_value(1920, 1920)
    with pytest.raises(ui.UserInputError, match="outside the desktop"):
        ui.absolute_value(-1, 1920)


def test_a_one_pixel_axis_maps_to_zero_and_steps_follow_the_axis_scale():
    assert ui.absolute_value(0, 1) == 0
    assert ui.absolute_step(10, 1920) == round(10 * ui.UINPUT_ABS_MAX / 1919)
    assert ui.absolute_step(-3, 1) == 0


# --- kernel event and ioctl encoding ----------------------------------------------------------

def test_kernel_ioctl_numbers_match_linux_uinput_h():
    assert ui.UI_DEV_CREATE == 0x5501
    assert ui.UI_DEV_DESTROY == 0x5502
    assert ui.UI_DEV_SETUP == 0x405C5503   # struct uinput_setup is 92 bytes
    assert ui.UI_ABS_SETUP == 0x401C5504   # struct uinput_abs_setup is 28 bytes
    assert ui.UI_SET_EVBIT == 0x40045564
    assert ui.UI_SET_KEYBIT == 0x40045565
    assert ui.UI_SET_ABSBIT == 0x40045567
    assert ui.UI_SET_PROPBIT == 0x4004556E
    assert struct.calcsize(ui._SETUP_FORMAT) == 92
    assert struct.calcsize(ui._ABS_SETUP_FORMAT) == 28


def test_input_event_uses_the_64_bit_kernel_layout():
    if ctypes.sizeof(ctypes.c_long) != 8:
        pytest.skip("the event layout check assumes LP64")
    assert struct.calcsize(ui._EVENT_FORMAT) == 24
    assert ui.encode_event(ui.EV_KEY, ui.BTN_LEFT, 1) == struct.pack("qqHHi", 0, 0, 1, 0x110, 1)


def test_abs_move_is_x_then_y_then_one_sync_report():
    assert ui.decode_events(ui.encode_abs_move(100, 200)) == [
        (ui.EV_ABS, ui.ABS_X, 100), (ui.EV_ABS, ui.ABS_Y, 200), (ui.EV_SYN, ui.SYN_REPORT, 0)]


def test_button_press_and_release_are_btn_left_each_with_a_sync_report():
    assert ui.decode_events(ui.encode_button(True)) == [
        (ui.EV_KEY, ui.BTN_LEFT, 1), (ui.EV_SYN, ui.SYN_REPORT, 0)]
    assert ui.decode_events(ui.encode_button(False)) == [
        (ui.EV_KEY, ui.BTN_LEFT, 0), (ui.EV_SYN, ui.SYN_REPORT, 0)]


# --- UinputDevice over a fake kernel ----------------------------------------------------------

class FakeKernel:
    """Records the uinput file operations. ``fail_on`` names an ioctl request that raises EINVAL."""

    FD = 7

    def __init__(self, *, fail_on=None, open_error=None):
        self.fail_on = fail_on
        self.open_error = open_error
        self.opened, self.ioctls, self.writes, self.closed = [], [], [], []

    def open(self, path, flags):
        if self.open_error is not None:
            raise self.open_error
        self.opened.append((path, flags))
        return self.FD

    def ioctl(self, fd, request, arg):
        assert fd == self.FD
        if request == self.fail_on:
            raise OSError(errno.EINVAL, "Invalid argument")
        self.ioctls.append((request, arg))
        return 0

    def write(self, fd, data):
        assert fd == self.FD
        self.writes.append(bytes(data))
        return len(data)

    def close(self, fd):
        self.closed.append(fd)

    def args(self, request):
        return [arg for name, arg in self.ioctls if name == request]


RealUinputDevice = ui.UinputDevice  # kept before any test patches the name


def make_device(kernel):
    return RealUinputDevice(path="/dev/uinput-under-test", ioctl=kernel.ioctl, open_fn=kernel.open,
                            write_fn=kernel.write, close_fn=kernel.close)


def test_create_enables_one_absolute_pointer_then_creates_it():
    kernel = FakeKernel()
    make_device(kernel).create()
    assert kernel.opened == [("/dev/uinput-under-test", os.O_WRONLY | os.O_NONBLOCK)]
    assert [name for name, _ in kernel.ioctls] == (
        [ui.UI_SET_EVBIT] * 3 + [ui.UI_SET_KEYBIT] + [ui.UI_SET_ABSBIT] * 2 + [ui.UI_SET_PROPBIT]
        + [ui.UI_ABS_SETUP] * 2 + [ui.UI_DEV_SETUP, ui.UI_DEV_CREATE])
    assert kernel.args(ui.UI_SET_EVBIT) == [ui.EV_SYN, ui.EV_KEY, ui.EV_ABS]
    assert kernel.args(ui.UI_SET_KEYBIT) == [ui.BTN_LEFT]
    assert kernel.args(ui.UI_SET_ABSBIT) == [ui.ABS_X, ui.ABS_Y]
    assert kernel.args(ui.UI_SET_PROPBIT) == [ui.INPUT_PROP_POINTER]
    axes = [struct.unpack("=Hxx6i", payload) for payload in kernel.args(ui.UI_ABS_SETUP)]
    assert [(code, minimum, maximum) for code, _value, minimum, maximum, _fuzz, _flat, _res in axes] == [
        (ui.ABS_X, 0, ui.UINPUT_ABS_MAX), (ui.ABS_Y, 0, ui.UINPUT_ABS_MAX)]
    bus, _vendor, _product, _version, name, ff_effects = struct.unpack(
        "=HHHH80sI", kernel.args(ui.UI_DEV_SETUP)[0])
    assert bus == ui.BUS_VIRTUAL and ff_effects == 0
    assert name.rstrip(b"\0").decode("ascii") == ui.UINPUT_DEVICE_NAME
    assert kernel.args(ui.UI_DEV_CREATE) == [0]


def test_abs_move_and_each_button_edge_are_written_as_whole_event_batches():
    kernel = FakeKernel()
    device = make_device(kernel)
    device.create()
    device.abs_move(100, 200)
    device.button(True)
    device.button(False)
    assert [ui.decode_events(write) for write in kernel.writes] == [
        [(ui.EV_ABS, ui.ABS_X, 100), (ui.EV_ABS, ui.ABS_Y, 200), (ui.EV_SYN, ui.SYN_REPORT, 0)],
        [(ui.EV_KEY, ui.BTN_LEFT, 1), (ui.EV_SYN, ui.SYN_REPORT, 0)],
        [(ui.EV_KEY, ui.BTN_LEFT, 0), (ui.EV_SYN, ui.SYN_REPORT, 0)],
    ]


@pytest.mark.parametrize("bad", [-1, ui.UINPUT_ABS_MAX + 1, 1.5, True])
def test_out_of_range_or_non_integer_absolute_values_are_refused_before_any_write(bad):
    kernel = FakeKernel()
    device = make_device(kernel)
    device.create()
    with pytest.raises(ui.UserInputError, match="outside 0"):
        device.abs_move(bad, 0)
    assert kernel.writes == []


def test_close_destroys_the_kernel_device_once_and_closes_the_descriptor_once():
    kernel = FakeKernel()
    device = make_device(kernel)
    device.create()
    device.close()
    device.close()
    assert kernel.args(ui.UI_DEV_DESTROY) == [0]
    assert kernel.closed == [FakeKernel.FD]
    with pytest.raises(ui.UserInputError, match="not created"):
        device.abs_move(1, 1)


def test_missing_or_unauthorised_uinput_is_refused_with_the_input_group_hint():
    kernel = FakeKernel(open_error=PermissionError(errno.EACCES, "Permission denied"))
    with pytest.raises(ui.UserInputError, match="group input"):
        make_device(kernel).create()


def test_a_failed_create_ioctl_closes_the_descriptor_and_leaves_no_device():
    kernel = FakeKernel(fail_on=ui.UI_DEV_CREATE)
    device = make_device(kernel)
    with pytest.raises(ui.UserInputError, match="cannot create"):
        device.create()
    assert kernel.closed == [FakeKernel.FD]
    assert ui.UI_DEV_CREATE not in [name for name, _ in kernel.ioctls]
    with pytest.raises(ui.UserInputError, match="not created"):
        device.abs_move(1, 1)


# --- verified moves over a simulated compositor -----------------------------------------------

class SimulatedCompositor:
    """Stands in for the compositor and the X root. Absolute motion lands at a fixed pixel error."""

    def __init__(self, desktop=(1920, 1080), error=(0, 0), ignore_motion=False):
        self.desktop = desktop
        self.error = error
        self.ignore_motion = ignore_motion
        self.position = (0, 0)
        self.abs_moves = []
        self.buttons = []

    def abs_move(self, x, y):
        self.abs_moves.append((x, y))
        if not self.ignore_motion:
            width, height = self.desktop
            self.position = (round(x * width / (ui.UINPUT_ABS_MAX + 1)) + self.error[0],
                             round(y * height / (ui.UINPUT_ABS_MAX + 1)) + self.error[1])

    def button(self, pressed):
        self.buttons.append(bool(pressed))

    def observe(self):
        return self.position


def make_pointer(compositor):
    return ui.UinputPointer(compositor, observe=compositor.observe, desktop=compositor.desktop)


def test_a_move_that_lands_within_tolerance_needs_no_correction(clock):
    compositor = SimulatedCompositor(error=(2, -2))
    pointer = make_pointer(compositor)
    record = pointer.move(350, 420)
    assert len(compositor.abs_moves) == 1
    assert record["landed"] is True and pointer.verified == (350, 420)


def test_a_constant_error_is_removed_by_a_bounded_corrective_move(clock):
    compositor = SimulatedCompositor(error=(7, -9))
    pointer = make_pointer(compositor)
    record = pointer.move(350, 420)
    assert record["landed"] is True and pointer.verified == (350, 420)
    assert 2 <= len(compositor.abs_moves) <= ui.POINTER_CORRECTIONS + 1
    assert len(record["attempts"]) == len(compositor.abs_moves)


def test_a_pointer_that_ignores_motion_is_refused_after_the_bounded_corrections(clock):
    compositor = SimulatedCompositor(ignore_motion=True)
    pointer = make_pointer(compositor)
    with pytest.raises(ui.UserInputError,
                       match=r"did not reach \(350, 420\) after 3 corrective uinput moves; it is at \(0, 0\)"):
        pointer.move(350, 420)
    assert len(compositor.abs_moves) == ui.POINTER_CORRECTIONS + 1
    assert pointer.verified is None and pointer.last_move["landed"] is False
    assert compositor.buttons == []


def test_a_press_is_refused_when_the_pointer_has_moved_since_it_was_verified(clock):
    compositor = SimulatedCompositor()
    pointer = make_pointer(compositor)
    pointer.move(350, 420)
    compositor.position = (900, 900)  # something else moved the pointer
    with pytest.raises(ui.UserInputError, match="no press sent"):
        pointer.button(1, True)
    assert compositor.buttons == []


def test_a_press_needs_a_verified_position_and_only_the_left_button_is_pressed(clock):
    compositor = SimulatedCompositor()
    pointer = make_pointer(compositor)
    with pytest.raises(ui.UserInputError, match="no verified pointer position"):
        pointer.button(1, True)
    assert compositor.buttons == []
    pointer.move(350, 420)
    pointer.button(1, True)
    pointer.button(1, False)
    assert compositor.buttons == [True, False]
    with pytest.raises(ui.UserInputError, match="left button"):
        pointer.button(2, True)
    assert compositor.buttons == [True, False]


def test_targets_outside_the_desktop_are_refused_without_any_motion(clock):
    compositor = SimulatedCompositor()
    pointer = make_pointer(compositor)
    with pytest.raises(ui.UserInputError, match="outside the desktop 1920x1080"):
        pointer.move(1920, 10)
    assert compositor.abs_moves == []


def test_a_multi_monitor_desktop_reaches_a_point_on_the_second_monitor(clock):
    compositor = SimulatedCompositor(desktop=(3840, 1080))
    pointer = make_pointer(compositor)
    pointer.move(2500, 540)
    assert pointer.verified == (2500, 540)


# --- relay protocol and the host helper -------------------------------------------------------

class RecordingDevice:
    """Stands in for UinputDevice inside the helper and records what it was asked to do."""

    def __init__(self, *, fail_create=None):
        self.fail_create = fail_create
        self.calls = []
        self.closed = False

    def create(self):
        if self.fail_create:
            raise ui.UserInputError(self.fail_create)

    def abs_move(self, x, y):
        self.calls.append(("abs_move", x, y))

    def button(self, pressed):
        self.calls.append(("button", pressed))

    def close(self):
        self.closed = True


def start_helper(root, device, **kwargs):
    outcome = {}

    def run():
        try:
            outcome["summary"] = helper.serve(root, device, settle_sec=0, poll_sec=0.001, **kwargs)
        except Exception as exc:  # the test reads it from the outcome
            outcome["error"] = exc

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, outcome


def test_relay_carries_moves_and_presses_and_the_helper_shuts_down_on_request(tmp_path):
    root = tmp_path / "uinput-relay"
    device = RecordingDevice()
    thread, outcome = start_helper(root, device)
    transport = ui.RelayTransport(root, ready_timeout_sec=5, response_timeout_sec=5)
    transport.abs_move(100, 200)
    transport.button(True)
    transport.button(False)
    (root / helper.SHUTDOWN_REQUEST).write_text("", encoding="utf-8")
    thread.join(5)
    assert not thread.is_alive()
    assert device.calls == [("abs_move", 100, 200), ("button", True), ("button", False)]
    assert device.closed is True
    assert outcome["summary"] == {"reason": helper.SHUTDOWN_REQUEST, "requests_served": 3, "close_error": None}
    stopped = json.loads((root / "stopped.json").read_text(encoding="utf-8"))
    assert stopped["reason"] == helper.SHUTDOWN_REQUEST and stopped["requests_served"] == 3
    assert json.loads((root / "ready.json").read_text(encoding="utf-8"))["abs_max"] == ui.UINPUT_ABS_MAX
    assert json.loads((root / "owner.json").read_text(encoding="utf-8"))["pid"] == os.getpid()


def test_an_out_of_range_move_is_refused_by_the_helper_and_never_reaches_the_device(tmp_path):
    root = tmp_path / "uinput-relay"
    device = RecordingDevice()
    thread, _outcome = start_helper(root, device)
    transport = ui.RelayTransport(root, ready_timeout_sec=5, response_timeout_sec=5)
    with pytest.raises(ui.UserInputError, match="uinput helper refused abs_move: ValueError"):
        transport.abs_move(ui.UINPUT_ABS_MAX + 1, 0)
    (root / helper.SHUTDOWN_REQUEST).write_text("", encoding="utf-8")
    thread.join(5)
    assert device.calls == []


def test_a_relay_without_a_helper_is_refused_when_it_is_not_ready(tmp_path):
    with pytest.raises(ui.UserInputError, match="is not ready after"):
        ui.RelayTransport(tmp_path / "empty", ready_timeout_sec=0.05)


def test_a_helper_that_does_not_answer_fails_the_request_loudly(tmp_path):
    root = tmp_path / "relay"
    ui.write_atomic_json(root / "ready.json", {"ready": True, "abs_max": ui.UINPUT_ABS_MAX})
    transport = ui.RelayTransport(root, ready_timeout_sec=1, response_timeout_sec=0.05)
    with pytest.raises(ui.UserInputError, match="did not answer abs_move"):
        transport.abs_move(1, 1)


def test_a_helper_that_cannot_create_the_pointer_says_so_and_writes_failed_json(tmp_path):
    root = tmp_path / "relay"
    thread, outcome = start_helper(root, RecordingDevice(fail_create="cannot open /dev/uinput: denied"))
    with pytest.raises(ui.UserInputError,
                       match="could not create the pointer: cannot open /dev/uinput: denied"):
        ui.RelayTransport(root, ready_timeout_sec=5)
    thread.join(5)
    assert json.loads((root / "failed.json").read_text(encoding="utf-8"))["error"] == \
        "cannot open /dev/uinput: denied"
    assert "error" in outcome


def test_an_idle_helper_destroys_its_device_and_records_why(tmp_path):
    root = tmp_path / "relay"
    device = RecordingDevice()
    summary = helper.serve(root, device, idle_timeout_sec=0.05, settle_sec=0, poll_sec=0.001)
    assert summary == {"reason": "idle timeout", "requests_served": 0, "close_error": None}
    assert device.closed is True
    assert json.loads((root / "stopped.json").read_text(encoding="utf-8"))["reason"] == "idle timeout"


def test_the_helper_answers_malformed_requests_without_touching_the_device():
    device = RecordingDevice()
    assert helper.execute(device, {"op": "wheel"}, "n1")["ok"] is False
    assert helper.execute(device, {"op": "button", "button": 2, "pressed": True}, "n2")["ok"] is False
    assert helper.execute(device, {"op": "button", "button": 1, "pressed": "yes"}, "n3")["ok"] is False
    assert helper.execute(device, {"op": "abs_move", "x": True, "y": 0}, "n4")["ok"] is False
    assert device.calls == []
    assert helper.execute(device, {"op": "abs_move", "x": 0, "y": ui.UINPUT_ABS_MAX}, "n5")["ok"] is True
    assert device.calls == [("abs_move", 0, ui.UINPUT_ABS_MAX)]


def test_a_relay_directory_already_used_by_a_helper_is_refused(tmp_path, capsys):
    relay = tmp_path / "relay"
    relay.mkdir()
    (relay / "owner.json").write_text("{}", encoding="utf-8")
    assert helper.main(["--relay-dir", str(relay)]) == 2
    assert "already used" in capsys.readouterr().err


# --- the backend wiring -----------------------------------------------------------------------

def test_the_uinput_backend_moves_through_the_relay_and_verifies_the_landing_at_x_level(tmp_path, monkeypatch):
    server = base.FakeXServer(desktop=(1920, 1080))
    monkeypatch.setattr(ui, "get_backend", lambda: ui.XTestBackend(*server.libraries()))
    monkeypatch.setattr(ui, "_UINPUT_BACKEND", None)
    root = tmp_path / "relay"
    monkeypatch.setenv(ui.UINPUT_RELAY_ENV, str(root))

    class LandingDevice(RecordingDevice):
        """Lands absolute motion on the fake X root, as the compositor would."""

        def abs_move(self, x, y):
            super().abs_move(x, y)
            server.pointer = (round(x * 1920 / (ui.UINPUT_ABS_MAX + 1)),
                              round(y * 1080 / (ui.UINPUT_ABS_MAX + 1)))

    device = LandingDevice()
    thread, _outcome = start_helper(root, device)
    backend = ui.get_uinput_backend()
    assert isinstance(backend, ui.UinputBackend)
    backend.move(960, 540)
    assert backend.last_move["landed"] is True
    backend.button(1, True)
    backend.button(1, False)
    (root / helper.SHUTDOWN_REQUEST).write_text("", encoding="utf-8")
    thread.join(5)
    assert [call[0] for call in device.calls] == ["abs_move", "button", "button"]
    assert device.calls[0][1:] == (round(960 * ui.UINPUT_ABS_MAX / 1919), round(540 * ui.UINPUT_ABS_MAX / 1079))


def test_without_a_relay_the_backend_opens_uinput_in_process_and_refuses_if_it_cannot(monkeypatch):
    server = base.FakeXServer()
    monkeypatch.setattr(ui, "get_backend", lambda: ui.XTestBackend(*server.libraries()))
    monkeypatch.setattr(ui, "_UINPUT_BACKEND", None)
    monkeypatch.delenv(ui.UINPUT_RELAY_ENV, raising=False)
    kernel = FakeKernel(open_error=PermissionError(errno.EACCES, "Permission denied"))
    monkeypatch.setattr(ui, "UinputDevice", lambda: make_device(kernel))  # the real class, fake kernel
    with pytest.raises(ui.UserInputError, match="group input"):
        ui.get_uinput_backend()
    assert ui._UINPUT_BACKEND is None


def test_xtest_and_demo_modes_keep_the_xtest_pointer_path(monkeypatch):
    server = base.FakeXServer()
    xbackend = ui.XTestBackend(*server.libraries())
    monkeypatch.setattr(ui, "get_backend", lambda: xbackend)
    monkeypatch.setattr(ui, "get_uinput_backend", lambda: pytest.fail("only uinput mode uses uinput"))
    assert ui.pointer_backend("xtest") is xbackend
    assert ui.pointer_backend("demo") is xbackend
    assert ui.pointer_backend("qt_click") is xbackend


def test_the_uinput_mode_is_accepted_from_the_environment():
    assert ui.input_mode_from_env({"DENTOBOT_HEADED_INPUT": "uinput"}) == "uinput"
    assert "uinput" in ui.MODES



def test_a_failed_device_close_is_recorded_and_the_shutdown_record_is_still_written(tmp_path):
    class BrokenCloseDevice(RecordingDevice):
        def close(self):
            raise ui.UserInputError("cannot destroy the uinput pointer: Input/output error")

    root = tmp_path / "relay"
    summary = helper.serve(root, BrokenCloseDevice(), idle_timeout_sec=0.02, settle_sec=0, poll_sec=0.001)
    assert summary["close_error"] == "cannot destroy the uinput pointer: Input/output error"
    stopped = json.loads((root / "stopped.json").read_text(encoding="utf-8"))
    assert stopped["reason"] == "idle timeout" and "Input/output error" in stopped["close_error"]
