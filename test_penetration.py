"""
Digital Twin Sanctuary — Penetration & State Consistency Test Suite
===================================================================
Verifies:
  1. Zero-Leak Security  — duplicate nonce + tampered payload attacks
  2. State Machine        — threshold breach → STASIS_LOCKED over WebSocket
"""

import asyncio
import json
import time

import websockets

from dts_core import (
    EphemeralKeyRotator,
    HardenedSentry,
    MemoryPool,
    compute_packet_hmac,
)
from dts_server import SystemState, TheLive

ANCHOR_KEY = b"dts_default_anchor_2024"
WS_URI = "ws://127.0.0.1:8888/graft"


# ======================================================================
# Unit-Level Tests (no server required)
# ======================================================================

def test_duplicate_nonce_blocked() -> None:
    """Send a valid packet then resend the same nonce — must be rejected."""
    pool = MemoryPool()
    rotator = EphemeralKeyRotator(ANCHOR_KEY)
    sentry = HardenedSentry(rotator, pool)

    ts = time.time()
    nonce = 1
    sensor_value = 42.5
    key = rotator.get_key_for_timestamp(ts)
    mac = compute_packet_hmac(key, sensor_value, ts, nonce)

    packet = {
        "timestamp": ts,
        "nonce": nonce,
        "hmac": mac,
        "payload": {"sensor_value": sensor_value},
    }

    ok, reason = sentry.validate(packet)
    assert ok, f"First packet should pass: {reason}"
    print("  [+] First packet accepted ✓")

    # Duplicate nonce attack
    ts2 = time.time()
    key2 = rotator.get_key_for_timestamp(ts2)
    mac2 = compute_packet_hmac(key2, sensor_value, ts2, nonce)  # same nonce=1
    dup_packet = {
        "timestamp": ts2,
        "nonce": nonce,  # duplicate
        "hmac": mac2,
        "payload": {"sensor_value": sensor_value},
    }

    ok2, reason2 = sentry.validate(dup_packet)
    assert not ok2, "Duplicate nonce should be rejected"
    assert "REPLAY_ATTACK" in reason2
    assert any(
        f["event"]["type"] == "REPLAY_ATTACK" for f in pool.friction_history
    ), "REPLAY_ATTACK must be in friction_history"
    print("  [+] Duplicate nonce BLOCKED and logged to Friction_History ✓")


def test_tampered_payload_blocked() -> None:
    """Sign a payload then modify the sensor_value — HMAC must mismatch."""
    pool = MemoryPool()
    rotator = EphemeralKeyRotator(ANCHOR_KEY)
    sentry = HardenedSentry(rotator, pool)

    ts = time.time()
    nonce = 1
    real_value = 55.0
    key = rotator.get_key_for_timestamp(ts)
    mac = compute_packet_hmac(key, real_value, ts, nonce)

    # Tamper: change sensor_value but keep original HMAC
    tampered_packet = {
        "timestamp": ts,
        "nonce": nonce,
        "hmac": mac,
        "payload": {"sensor_value": 0.0},  # tampered
    }

    ok, reason = sentry.validate(tampered_packet)
    assert not ok, "Tampered payload should be rejected"
    assert "HMAC_MISMATCH" in reason
    assert any(
        f["event"]["type"] == "HMAC_MISMATCH" for f in pool.friction_history
    ), "HMAC_MISMATCH must be in friction_history"
    print("  [+] Tampered payload BLOCKED and logged to Friction_History ✓")


def test_stasis_lock_on_breach() -> None:
    """Simulate a sensor value crossing the critical threshold.
    Backend must transition to STASIS_LOCKED and break phase locks."""
    runtime = TheLive(anchor_key=ANCHOR_KEY)

    # Add a symbiotic phase lock to verify it gets broken
    runtime.symbiotic_phase_locks.extend(["LOCK_A", "LOCK_B"])
    assert len(runtime.symbiotic_phase_locks) == 2

    # Send a value above BREACH_THRESHOLD (95.0)
    state = runtime.evaluate_node_state({"sensor_value": 97.3})
    assert state == SystemState.STASIS_LOCKED, f"Expected STASIS_LOCKED, got {state}"
    assert len(runtime.symbiotic_phase_locks) == 0, "Phase locks must be cleared on breach"

    snapshot = runtime.get_state_snapshot()
    assert snapshot["state"] == "STASIS_LOCKED"
    print("  [+] STASIS_LOCKED triggered, phase locks broken ✓")


def test_drift_progression() -> None:
    """Verify progressive state transitions: SYNCED → DRIFT → BREACH."""
    runtime = TheLive(anchor_key=ANCHOR_KEY)
    assert runtime.state == SystemState.SYNCED

    # Drift level 1
    runtime.evaluate_node_state({"sensor_value": 82.0})
    assert runtime.state == SystemState.DRIFT_LEVEL_1
    print("  [+] SYNCED → DRIFT_LEVEL_1 on moderate value ✓")

    # Another drift pushes to breach
    runtime.evaluate_node_state({"sensor_value": 85.0})
    assert runtime.state == SystemState.BREACH_LEVEL_2
    print("  [+] DRIFT_LEVEL_1 → BREACH_LEVEL_2 on sustained drift ✓")


def test_memory_pool_compression() -> None:
    """Verify age_and_compress_telemetry compresses old data ~95%."""
    from dts_core import age_and_compress_telemetry

    pool = MemoryPool()

    # Insert 200 old entries (>72h ago)
    for i in range(200):
        pool.live_stream.append({
            "ingested_at": time.time() - 80 * 3600,
            "data": {"sensor_value": float(i), "temp": 20.0 + i * 0.05},
        })
    # Insert 10 recent entries
    for i in range(10):
        pool.ingest({"sensor_value": float(i), "temp": 25.0})

    original_count = len(pool.live_stream)
    footprint = age_and_compress_telemetry(pool)

    assert footprint["source_count"] == 200
    assert len(pool.live_stream) == 10  # only recent retained
    reduction = 1.0 - (len(pool.live_stream) / original_count)
    assert reduction >= 0.90, f"Compression only {reduction:.0%}"
    print(f"  [+] Compressed {original_count} → {len(pool.live_stream)} entries ({reduction:.0%} reduction) ✓")


def test_foundry_progression() -> None:
    """Verify FoundryModule increments wisdom_yield on peer validation."""
    from dts_core import FoundryModule

    pool = MemoryPool()
    foundry = FoundryModule()

    sig = "SIG_ALPHA"

    # Not enough validators yet
    pool.add_insight(sig, {"text": "a", "validated_by": "SIG_B"})
    pool.add_insight(sig, {"text": "b", "validated_by": "SIG_C"})
    wy = foundry.evaluate_progression(sig, pool)
    assert wy == 0.0, "Should not progress with < 3 validators"
    print("  [+] No progression with < 3 validators ✓")

    # Third unique validator crosses threshold
    pool.add_insight(sig, {"text": "c", "validated_by": "SIG_D"})
    wy = foundry.evaluate_progression(sig, pool)
    assert wy == 0.1, f"Expected 0.1, got {wy}"
    print("  [+] wisdom_yield incremented to 0.1 on 3rd validator ✓")


# ======================================================================
# Integration Tests (require running server)
# ======================================================================

async def test_ws_valid_then_replay_attack() -> None:
    """Connect via WebSocket, send valid packet, then replay nonce."""
    rotator = EphemeralKeyRotator(ANCHOR_KEY)

    async with websockets.connect(WS_URI) as ws:
        # Valid packet
        ts = time.time()
        nonce = 5000  # high nonce to avoid collision with unit tests
        sv = 42.0
        key = rotator.get_key_for_timestamp(ts)
        mac = compute_packet_hmac(key, sv, ts, nonce)
        packet = {"timestamp": ts, "nonce": nonce, "hmac": mac, "payload": {"sensor_value": sv}}
        await ws.send(json.dumps(packet))
        resp = json.loads(await ws.recv())
        assert resp["status"] == "ACCEPTED", f"Valid packet rejected: {resp}"
        print("  [+] WS valid packet accepted ✓")

    # New connection for replay
    async with websockets.connect(WS_URI) as ws2:
        ts2 = time.time()
        key2 = rotator.get_key_for_timestamp(ts2)
        mac2 = compute_packet_hmac(key2, sv, ts2, nonce)  # same nonce
        replay_packet = {"timestamp": ts2, "nonce": nonce, "hmac": mac2, "payload": {"sensor_value": sv}}
        await ws2.send(json.dumps(replay_packet))
        resp2 = json.loads(await ws2.recv())
        assert resp2["status"] == "CIRCUIT_BREAK", f"Replay not blocked: {resp2}"
        assert "REPLAY" in resp2["reason"]
        print("  [+] WS replay attack → CIRCUIT_BREAK ✓")


async def test_ws_tampered_payload() -> None:
    """Send tampered payload over WebSocket — expect CIRCUIT_BREAK."""
    rotator = EphemeralKeyRotator(ANCHOR_KEY)

    async with websockets.connect(WS_URI) as ws:
        ts = time.time()
        nonce = 6000
        real_sv = 50.0
        key = rotator.get_key_for_timestamp(ts)
        mac = compute_packet_hmac(key, real_sv, ts, nonce)

        tampered = {"timestamp": ts, "nonce": nonce, "hmac": mac, "payload": {"sensor_value": 0.0}}
        await ws.send(json.dumps(tampered))
        resp = json.loads(await ws.recv())
        assert resp["status"] == "CIRCUIT_BREAK"
        assert "HMAC_MISMATCH" in resp["reason"]
        print("  [+] WS tampered payload → CIRCUIT_BREAK ✓")


async def test_ws_stasis_broadcast() -> None:
    """Send a critical-threshold payload and verify STASIS_LOCKED is pushed."""
    rotator = EphemeralKeyRotator(ANCHOR_KEY)

    # UI subscriber listens for state updates
    async with websockets.connect(WS_URI) as ui_ws:
        await ui_ws.send(json.dumps({"type": "UI_SUBSCRIBE"}))
        init = json.loads(await ui_ws.recv())
        assert init["type"] == "STATE_UPDATE"
        print(f"  [+] UI subscribed, initial state: {init['state']} ✓")

        # Node connection sends critical value
        async with websockets.connect(WS_URI) as node_ws:
            ts = time.time()
            nonce = 7000
            sv = 99.0  # above BREACH_THRESHOLD
            key = rotator.get_key_for_timestamp(ts)
            mac = compute_packet_hmac(key, sv, ts, nonce)
            packet = {"timestamp": ts, "nonce": nonce, "hmac": mac, "payload": {"sensor_value": sv}}
            await node_ws.send(json.dumps(packet))
            node_resp = json.loads(await node_ws.recv())
            assert node_resp["status"] == "ACCEPTED"
            assert node_resp["state"] == "STASIS_LOCKED"
            print("  [+] Node received STASIS_LOCKED confirmation ✓")

        # UI should receive broadcast
        broadcast = json.loads(await asyncio.wait_for(ui_ws.recv(), timeout=3.0))
        assert broadcast["type"] == "STATE_UPDATE"
        assert broadcast["state"] == "STASIS_LOCKED"
        print("  [+] UI received STASIS_LOCKED broadcast ✓")


# ======================================================================
# Runner
# ======================================================================

def run_unit_tests() -> None:
    print("\n" + "=" * 60)
    print("UNIT TESTS — Zero-Leak Security & State Machine")
    print("=" * 60)

    print("\n[TEST] Duplicate Nonce Attack")
    test_duplicate_nonce_blocked()

    print("\n[TEST] Tampered Payload Attack")
    test_tampered_payload_blocked()

    print("\n[TEST] STASIS_LOCKED on Breach")
    test_stasis_lock_on_breach()

    print("\n[TEST] Drift State Progression")
    test_drift_progression()

    print("\n[TEST] Memory Pool Compression")
    test_memory_pool_compression()

    print("\n[TEST] FoundryModule Progression")
    test_foundry_progression()

    print("\n" + "-" * 60)
    print("ALL UNIT TESTS PASSED")
    print("-" * 60)


async def run_integration_tests() -> None:
    print("\n" + "=" * 60)
    print("INTEGRATION TESTS — WebSocket Graft Point")
    print("=" * 60)

    print("\n[TEST] WS Valid + Replay Attack")
    await test_ws_valid_then_replay_attack()

    print("\n[TEST] WS Tampered Payload")
    await test_ws_tampered_payload()

    print("\n[TEST] WS STASIS_LOCKED Broadcast")
    await test_ws_stasis_broadcast()

    print("\n" + "-" * 60)
    print("ALL INTEGRATION TESTS PASSED")
    print("-" * 60)


if __name__ == "__main__":
    import sys

    run_unit_tests()

    if "--integration" in sys.argv:
        print("\nStarting integration tests (server must be running on :8888)...")
        asyncio.run(run_integration_tests())
    else:
        print("\nSkipping integration tests. Run with --integration flag")
        print("(ensure server is running: python dts_server.py)")

    print("\n" + "=" * 60)
    print("TEST SUITE COMPLETE")
    print("=" * 60)
