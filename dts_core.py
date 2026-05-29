"""
Digital Twin Sanctuary (DTS) — Core Data Structures & Cryptographic Engine
==========================================================================
Phase 1: MemoryPool, age_and_compress_telemetry, FoundryModule
Phase 2: EphemeralKeyRotator, HardenedSentry
"""

import time
import hmac
import hashlib
import statistics
from dataclasses import dataclass, field
from typing import Any


# ---------------------------------------------------------------------------
# Phase 1 — Core Data Structures & Memory Pool
# ---------------------------------------------------------------------------

class MemoryPool:
    """Central storage schema replacing traditional database/datastore concepts.

    Stores:
        live_stream          — raw telemetry dict logs with timestamps.
        friction_history     — captured errors / breach events.
        community_insights   — peer feedback keyed by Signal_Signature.
    """

    def __init__(self) -> None:
        self.live_stream: list[dict[str, Any]] = []
        self.friction_history: list[dict[str, Any]] = []
        self.community_insights: dict[str, list[dict[str, Any]]] = {}
        self.spectral_footprints: list[dict[str, Any]] = []

    def ingest(self, payload: dict[str, Any]) -> None:
        """Ingest a validated telemetry payload into live_stream."""
        entry = {
            "ingested_at": time.time(),
            "data": payload,
        }
        self.live_stream.append(entry)

    def log_friction(self, event: dict[str, Any]) -> None:
        """Record a friction event (error / breach) into friction_history."""
        record = {
            "logged_at": time.time(),
            "event": event,
        }
        self.friction_history.append(record)

    def add_insight(self, signal_signature: str, insight: dict[str, Any]) -> None:
        """Append a community insight for a given Signal_Signature."""
        if signal_signature not in self.community_insights:
            self.community_insights[signal_signature] = []
        self.community_insights[signal_signature].append(insight)

    def get_insights(self, signal_signature: str) -> list[dict[str, Any]]:
        """Retrieve all community insights for a Signal_Signature."""
        return self.community_insights.get(signal_signature, [])


def age_and_compress_telemetry(pool: MemoryPool, max_age_hours: float = 72.0) -> dict[str, Any]:
    """Data-aging sequence: compress raw logs older than *max_age_hours*
    into a summarized spectral_footprint, reducing memory overhead ~95%.

    Returns the spectral_footprint dict (empty dict if nothing was aged).
    """
    cutoff = time.time() - (max_age_hours * 3600)

    aged_entries: list[dict[str, Any]] = []
    retained: list[dict[str, Any]] = []

    for entry in pool.live_stream:
        if entry["ingested_at"] < cutoff:
            aged_entries.append(entry)
        else:
            retained.append(entry)

    if not aged_entries:
        return {}

    numeric_fields: dict[str, list[float]] = {}
    for entry in aged_entries:
        data = entry.get("data", {})
        for key, value in data.items():
            if isinstance(value, (int, float)):
                numeric_fields.setdefault(key, []).append(float(value))

    spectral_footprint: dict[str, Any] = {
        "compressed_at": time.time(),
        "source_count": len(aged_entries),
        "time_range": {
            "oldest": min(e["ingested_at"] for e in aged_entries),
            "newest": max(e["ingested_at"] for e in aged_entries),
        },
        "aggregates": {},
    }

    for field_name, values in numeric_fields.items():
        spectral_footprint["aggregates"][field_name] = {
            "min": min(values),
            "max": max(values),
            "avg": round(statistics.mean(values), 4),
            "count": len(values),
        }

    pool.live_stream = retained
    pool.spectral_footprints.append(spectral_footprint)
    return spectral_footprint


class FoundryModule:
    """Progression matrix tracking user experience (wisdom_yield)
    when community_insights achieve peer validation.
    """

    VALIDATION_THRESHOLD = 3   # unique validators required
    WISDOM_DELTA = 0.1         # increment per validated cycle

    def __init__(self) -> None:
        self._wisdom: dict[str, float] = {}

    def get_wisdom_yield(self, signal_signature: str) -> float:
        return self._wisdom.get(signal_signature, 0.0)

    def evaluate_progression(
        self, signal_signature: str, pool: MemoryPool
    ) -> float:
        """Check if a user's community_insights have received peer
        validation (>= VALIDATION_THRESHOLD unique validators).
        If so, increment wisdom_yield and return the new level.
        """
        insights = pool.get_insights(signal_signature)
        validators: set[str] = set()
        for insight in insights:
            validator = insight.get("validated_by")
            if validator and validator != signal_signature:
                validators.add(validator)

        if len(validators) >= self.VALIDATION_THRESHOLD:
            current = self._wisdom.get(signal_signature, 0.0)
            new_yield = min(current + self.WISDOM_DELTA, 1.0)
            self._wisdom[signal_signature] = round(new_yield, 4)

        return self.get_wisdom_yield(signal_signature)


# ---------------------------------------------------------------------------
# Phase 2 — Rotating Cryptographic Handshake
# ---------------------------------------------------------------------------

class EphemeralKeyRotator:
    """Time-Based Key Derivation Function (KDF) using HMAC-SHA256.

    Derives a new hourly_key each UTC hour:
        hourly_key = HMAC-SHA256(anchor_key, hour_timestamp_bytes)
    """

    def __init__(self, anchor_key: bytes) -> None:
        self._anchor_key = anchor_key

    def _hour_stamp(self, ts: float) -> bytes:
        """Return the UTC-hour bucket as bytes for a given Unix timestamp."""
        hour_bucket = int(ts) // 3600
        return str(hour_bucket).encode()

    def get_current_key(self) -> bytes:
        return self.get_key_for_timestamp(time.time())

    def get_key_for_timestamp(self, ts: float) -> bytes:
        return hmac.new(
            self._anchor_key,
            self._hour_stamp(ts),
            hashlib.sha256,
        ).digest()


def build_hmac_message(sensor_value: Any, timestamp: float, nonce: int) -> bytes:
    """Canonical HMAC payload format shared by backend and frontend:
        [sensor_value]-[timestamp]-[nonce]
    """
    return f"{sensor_value}-{timestamp}-{nonce}".encode()


def compute_packet_hmac(key: bytes, sensor_value: Any, timestamp: float, nonce: int) -> str:
    """Compute the hex-encoded HMAC for a telemetry packet."""
    message = build_hmac_message(sensor_value, timestamp, nonce)
    return hmac.new(key, message, hashlib.sha256).hexdigest()


class HardenedSentry:
    """Edge-node ingestion validator — drops packets that fail any of:
        1. 500 ms network-latency window check
        2. Anti-replay nonce check
        3. HMAC-SHA256 signature integrity check

    All rejections are routed to the MemoryPool's friction_history.
    """

    LATENCY_WINDOW = 0.5  # seconds

    def __init__(self, rotator: EphemeralKeyRotator, pool: MemoryPool) -> None:
        self._rotator = rotator
        self._pool = pool
        self._last_nonce: int = 0

    def validate(self, packet: dict[str, Any]) -> tuple[bool, str]:
        """Validate an incoming packet. Returns (is_valid, reason)."""
        ts = packet.get("timestamp", 0.0)
        nonce = packet.get("nonce", 0)
        packet_hmac = packet.get("hmac", "")
        payload = packet.get("payload", {})
        sensor_value = payload.get("sensor_value", "")

        # 1 — Latency window
        drift = abs(time.time() - ts)
        if drift > self.LATENCY_WINDOW:
            reason = f"LATENCY_VIOLATION: drift={drift:.4f}s exceeds {self.LATENCY_WINDOW}s window"
            self._pool.log_friction({
                "type": "LATENCY_VIOLATION",
                "packet_timestamp": ts,
                "drift": drift,
            })
            return False, reason

        # 2 — Anti-replay
        if nonce <= self._last_nonce:
            reason = f"REPLAY_ATTACK: nonce={nonce} <= last_processed={self._last_nonce}"
            self._pool.log_friction({
                "type": "REPLAY_ATTACK",
                "nonce": nonce,
                "last_processed_nonce": self._last_nonce,
            })
            return False, reason

        # 3 — HMAC integrity
        key = self._rotator.get_key_for_timestamp(ts)
        expected_hmac = compute_packet_hmac(key, sensor_value, ts, nonce)
        if not hmac.compare_digest(expected_hmac, packet_hmac):
            reason = "HMAC_MISMATCH: packet signature does not match derived key hash"
            self._pool.log_friction({
                "type": "HMAC_MISMATCH",
                "expected": expected_hmac,
                "received": packet_hmac,
            })
            return False, reason

        # All checks passed — advance nonce watermark
        self._last_nonce = nonce
        return True, "VALIDATED"
