"""Loads signals.yaml into a SignalConfig, with mtime-based hot reload.

Kept separate from signals.py so the signal engine itself stays pure
(no file I/O in the tested math).
"""
from __future__ import annotations

import threading
from pathlib import Path

import yaml

from signals import SignalConfig

CONFIG_PATH = Path(__file__).resolve().parent / "signals.yaml"

_lock = threading.Lock()
_cached_cfg: SignalConfig | None = None
_cached_raw: dict = {}
_cached_mtime: float | None = None


def _read() -> tuple[SignalConfig, dict]:
    raw = yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8")) or {}
    if not isinstance(raw, dict):
        raise ValueError("signals.yaml must contain a mapping at the top level")
    return SignalConfig.from_dict(raw), raw


def get_signal_config() -> SignalConfig:
    """Current SignalConfig; re-reads signals.yaml when its mtime changes."""
    global _cached_cfg, _cached_raw, _cached_mtime
    with _lock:
        try:
            mtime = CONFIG_PATH.stat().st_mtime
        except FileNotFoundError:
            _cached_cfg, _cached_raw, _cached_mtime = SignalConfig(), {}, None
            return _cached_cfg
        if _cached_cfg is None or mtime != _cached_mtime:
            _cached_cfg, _cached_raw = _read()
            _cached_mtime = mtime
        return _cached_cfg


def get_backtest_settings() -> dict:
    """Backtest section of signals.yaml (initial_cash, fee_bps)."""
    get_signal_config()  # refresh cache if stale
    with _lock:
        bt = _cached_raw.get("backtest", {}) or {}
    return {
        "initial_cash": float(bt.get("initial_cash", 10_000)),
        "fee_bps": float(bt.get("fee_bps", 10)),
    }
