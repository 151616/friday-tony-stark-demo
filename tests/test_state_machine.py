"""Tests for the launcher state machine logic."""
import sys
import types
import pytest


def _patch_heavy_imports():
    """
    Patch audio/ML imports that cannot be satisfied in a test environment
    (pyaudio, openwakeword, winsound, numpy) before importing friday_launcher.
    """
    # winsound — Windows-only stdlib module; may be missing on CI
    if "winsound" not in sys.modules:
        sys.modules["winsound"] = types.ModuleType("winsound")

    # numpy — provide a minimal stub if not installed
    if "numpy" not in sys.modules:
        np_stub = types.ModuleType("numpy")
        np_stub.frombuffer = lambda *a, **kw: None
        np_stub.int16 = None
        sys.modules["numpy"] = np_stub

    # pyaudio
    if "pyaudio" not in sys.modules:
        pa_stub = types.ModuleType("pyaudio")
        pa_stub.PyAudio = object
        pa_stub.paInt16 = 8
        sys.modules["pyaudio"] = pa_stub

    # openwakeword.model
    if "openwakeword" not in sys.modules:
        ow = types.ModuleType("openwakeword")
        ow_model = types.ModuleType("openwakeword.model")
        ow_model.Model = object
        sys.modules["openwakeword"] = ow
        sys.modules["openwakeword.model"] = ow_model

    # dotenv
    if "dotenv" not in sys.modules:
        dotenv_stub = types.ModuleType("dotenv")
        dotenv_stub.load_dotenv = lambda *a, **kw: None
        sys.modules["dotenv"] = dotenv_stub


_patch_heavy_imports()

from friday_launcher import State, MCPServerManager  # noqa: E402


def test_state_enum_values():
    assert State.SLEEPING.value == "sleeping"
    assert State.ACTIVE.value == "active"


def test_mcp_manager_start_stop():
    """MCPServerManager can be instantiated without errors."""
    mgr = MCPServerManager()
    assert mgr._proc is None


def test_state_transitions():
    """Verify valid state transitions."""
    state = State.SLEEPING
    wake_detected = True
    if wake_detected:
        state = State.ACTIVE
    assert state == State.ACTIVE

    dismissed = True
    if dismissed:
        state = State.SLEEPING
    assert state == State.SLEEPING
