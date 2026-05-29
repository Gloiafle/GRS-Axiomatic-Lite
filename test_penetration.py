"""
Digital Twin Sanctuary — Penetration & State Consistency Test Suite
===================================================================
Verifies:
  1. Zero-Leak Security  — duplicate nonce + tampered payload attacks
  2. State Machine        — threshold breach → STASIS_LOCKED over WebSocket
  3. Macro Mesh           — P2P TCP concurrency, RESONANCE_DEFICIT_BROADCAST,
                            CROSS_ANCESTRY_AUDIT_REQUEST
"""

import asyncio
import json
import time

import websockets

from dts_core import (
    EphemeralKeyRotator,
    HardenedSentry,
    MaterialRegistry,
    MemoryPool,
    TheAncestry,
    compute_packet_hmac,
)
from dts_server import SystemState, TheLive

ANCHOR_KEY = b"dts_default_anchor_2024"
WS_URI = "ws://127.0.0.1:8888/graft"
MACRO_MESH_HOST = "127.0.0.1"
MACRO_MESH_PORT = 8899


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


def test_material_registry() -> None:
    """Verify MaterialRegistry stores materials and deficit broadcasts."""
    registry = MaterialRegistry()

    registry.register_material("MAT_001", {"type": "resonance_crystal", "purity": 0.98})
    mat = registry.get_material("MAT_001")
    assert mat is not None
    assert mat["properties"]["purity"] == 0.98
    print("  [+] Material registered and retrieved ✓")

    registry.record_resonance_deficit({
        "source": "NODE_ALPHA",
        "deficit": {"frequency": 440.0, "magnitude": -12.5},
    })
    assert len(registry.get_deficit_log()) == 1
    snap = registry.get_registry_snapshot()
    assert snap["material_count"] == 1
    assert snap["deficit_broadcasts"] == 1
    print("  [+] Resonance deficit recorded and snapshot correct ✓")


def test_ancestry_chain() -> None:
    """Verify TheAncestry builds a cryptographically linked chain."""
    ancestry = TheAncestry()

    # Genesis block
    head = ancestry.get_head_block()
    assert head.index == 0
    assert head.previous_hash == "0" * 64
    assert len(head.block_hash) == 64
    print(f"  [+] Genesis block: index=0, hash={head.block_hash[:16]}... ✓")

    # Append blocks
    b1 = ancestry.append_block({"type": "TELEMETRY", "value": 42})
    assert b1.index == 1
    assert b1.previous_hash == head.block_hash
    b2 = ancestry.append_block({"type": "AUDIT", "result": "pass"})
    assert b2.index == 2
    assert b2.previous_hash == b1.block_hash
    print(f"  [+] Chain extended to length {ancestry.get_chain_length()} ✓")

    # Integrity check
    assert ancestry.verify_chain_integrity()
    print("  [+] Chain integrity verified ✓")

    # Audit response
    audit = ancestry.get_audit_response()
    assert audit["type"] == "CROSS_ANCESTRY_AUDIT_RESPONSE"
    assert audit["head_index"] == 2
    assert audit["head_hash"] == b2.block_hash
    assert audit["chain_length"] == 3
    print(f"  [+] Audit response: head_index={audit['head_index']}, hash={audit['head_hash'][:16]}... ✓")


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
# Macro Mesh Integration Tests (require server on :8888 + :8899)
# ======================================================================

async def _tcp_send_recv(frame: dict) -> dict:
    """Send a newline-delimited JSON frame to the Macro Mesh TCP port
    and return the parsed response."""
    reader, writer = await asyncio.open_connection(MACRO_MESH_HOST, MACRO_MESH_PORT)
    writer.write((json.dumps(frame) + "\n").encode())
    await writer.drain()
    data = await asyncio.wait_for(reader.readline(), timeout=5.0)
    writer.close()
    await writer.wait_closed()
    return json.loads(data.decode().strip())


async def test_resonance_deficit_broadcast() -> None:
    """Send a RESONANCE_DEFICIT_BROADCAST to :8899 and verify acknowledgement."""
    frame = {
        "type": "RESONANCE_DEFICIT_BROADCAST",
        "source": "NODE_BETA",
        "deficit": {"frequency": 528.0, "magnitude": -8.3},
    }
    resp = await _tcp_send_recv(frame)
    assert resp["status"] == "DEFICIT_ACKNOWLEDGED", f"Unexpected: {resp}"
    assert resp["registry_snapshot"]["deficit_broadcasts"] >= 1
    print("  [+] RESONANCE_DEFICIT_BROADCAST acknowledged ✓")
    print(f"      Registry: {resp['registry_snapshot']['deficit_broadcasts']} deficit(s) logged")


async def test_cross_ancestry_audit() -> None:
    """Send a CROSS_ANCESTRY_AUDIT_REQUEST and verify head block response."""
    frame = {"type": "CROSS_ANCESTRY_AUDIT_REQUEST"}
    resp = await _tcp_send_recv(frame)
    assert resp["type"] == "CROSS_ANCESTRY_AUDIT_RESPONSE", f"Unexpected: {resp}"
    assert isinstance(resp["head_index"], int)
    assert isinstance(resp["head_hash"], str)
    assert len(resp["head_hash"]) == 64  # SHA-256 hex
    assert resp["chain_length"] >= 1
    print(f"  [+] CROSS_ANCESTRY_AUDIT_RESPONSE received ✓")
    print(f"      head_index={resp['head_index']}, chain_length={resp['chain_length']}")
    print(f"      head_hash={resp['head_hash'][:32]}...")


async def test_macro_mesh_unknown_frame() -> None:
    """Send an unknown frame type and verify error response."""
    frame = {"type": "BOGUS_FRAME", "data": "test"}
    resp = await _tcp_send_recv(frame)
    assert resp["status"] == "ERROR"
    assert "Unknown frame type" in resp["reason"]
    print("  [+] Unknown frame type rejected with error ✓")


async def test_dual_port_concurrency() -> None:
    """Verify both :8888 (WebSocket) and :8899 (TCP) serve concurrently
    without thread blocking."""
    rotator = EphemeralKeyRotator(ANCHOR_KEY)

    # Prepare WebSocket task
    async def ws_task() -> str:
        async with websockets.connect(WS_URI) as ws:
            await ws.send(json.dumps({"type": "UI_SUBSCRIBE"}))
            resp = json.loads(await ws.recv())
            return resp["type"]

    # Prepare TCP task
    async def tcp_task() -> str:
        frame = {"type": "CROSS_ANCESTRY_AUDIT_REQUEST"}
        resp = await _tcp_send_recv(frame)
        return resp["type"]

    # Run both concurrently
    ws_result, tcp_result = await asyncio.gather(ws_task(), tcp_task())

    assert ws_result == "STATE_UPDATE", f"WS returned: {ws_result}"
    assert tcp_result == "CROSS_ANCESTRY_AUDIT_RESPONSE", f"TCP returned: {tcp_result}"
    print("  [+] Dual-port concurrent requests served without blocking ✓")
    print(f"      WS(:8888) → {ws_result}, TCP(:8899) → {tcp_result}")


async def test_deficit_then_audit_chain_grows() -> None:
    """Send a deficit broadcast, then audit — verify the chain grew."""
    # Get initial chain length
    audit1 = await _tcp_send_recv({"type": "CROSS_ANCESTRY_AUDIT_REQUEST"})
    initial_length = audit1["chain_length"]

    # Send a deficit broadcast (appends a block)
    deficit = {
        "type": "RESONANCE_DEFICIT_BROADCAST",
        "source": "NODE_GAMMA",
        "deficit": {"frequency": 396.0, "magnitude": -5.0},
    }
    await _tcp_send_recv(deficit)

    # Re-audit
    audit2 = await _tcp_send_recv({"type": "CROSS_ANCESTRY_AUDIT_REQUEST"})
    assert audit2["chain_length"] == initial_length + 1, (
        f"Chain should grow by 1: {initial_length} → {audit2['chain_length']}"
    )
    assert audit2["head_index"] == audit1["head_index"] + 1
    print(f"  [+] Chain grew: {initial_length} → {audit2['chain_length']} after deficit broadcast ✓")


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

    print("\n[TEST] MaterialRegistry")
    test_material_registry()

    print("\n[TEST] TheAncestry Chain")
    test_ancestry_chain()

    print("\n" + "-" * 60)
    print("ALL UNIT TESTS PASSED")
    print("-" * 60)


async def run_integration_tests() -> None:
    print("\n" + "=" * 60)
    print("INTEGRATION TESTS — WebSocket Graft Point (:8888)")
    print("=" * 60)

    print("\n[TEST] WS Valid + Replay Attack")
    await test_ws_valid_then_replay_attack()

    print("\n[TEST] WS Tampered Payload")
    await test_ws_tampered_payload()

    print("\n[TEST] WS STASIS_LOCKED Broadcast")
    await test_ws_stasis_broadcast()

    print("\n" + "-" * 60)
    print("ALL WEBSOCKET INTEGRATION TESTS PASSED")
    print("-" * 60)

    print("\n" + "=" * 60)
    print("MACRO MESH TESTS — P2P TCP Graft Point (:8899)")
    print("=" * 60)

    print("\n[TEST] Dual-Port Async Concurrency")
    await test_dual_port_concurrency()

    print("\n[TEST] RESONANCE_DEFICIT_BROADCAST")
    await test_resonance_deficit_broadcast()

    print("\n[TEST] CROSS_ANCESTRY_AUDIT_REQUEST")
    await test_cross_ancestry_audit()

    print("\n[TEST] Unknown Frame Rejection")
    await test_macro_mesh_unknown_frame()

    print("\n[TEST] Deficit → Audit Chain Growth")
    await test_deficit_then_audit_chain_grows()

    print("\n" + "-" * 60)
    print("ALL MACRO MESH TESTS PASSED")
    print("-" * 60)


if __name__ == "__main__":
    import sys

    run_unit_tests()

    if "--integration" in sys.argv:
        print("\nStarting integration tests (server must be running on :8888 + :8899)...")
        asyncio.run(run_integration_tests())
    else:
        print("\nSkipping integration tests. Run with --integration flag")
        print("(ensure server is running: python dts_server.py)")
        print("  :8888 = WebSocket Graft Point")
        print("  :8899 = Macro Mesh TCP P2P Port")

    print("\n" + "=" * 60)
    print("TEST SUITE COMPLETE")
    print("=" * 60)
