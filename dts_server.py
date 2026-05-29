"""
Digital Twin Sanctuary (DTS) — Asynchronous Network Graft Point
================================================================
Phase 3: TheLive runtime + NetworkGraftServer (FastAPI WebSocket)
Macro Mesh: P2P TCP socket server on :8899
"""

import asyncio
import json
import os
import time
from enum import Enum
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from dts_core import (
    EphemeralKeyRotator,
    FoundryModule,
    HardenedSentry,
    MaterialRegistry,
    MemoryPool,
    TheAncestry,
    age_and_compress_telemetry,
)


# ---------------------------------------------------------------------------
# System State Enumeration
# ---------------------------------------------------------------------------

class SystemState(str, Enum):
    SYNCED = "SYNCED"
    DRIFT_LEVEL_1 = "DRIFT_LEVEL_1"
    BREACH_LEVEL_2 = "BREACH_LEVEL_2"
    STASIS_LOCKED = "STASIS_LOCKED"


# ---------------------------------------------------------------------------
# TheLive — Core Operational Runtime
# ---------------------------------------------------------------------------

class TheLive:
    """Main execution runtime replacing traditional main loops.

    Orchestrates MemoryPool, EphemeralKeyRotator, HardenedSentry,
    FoundryModule, and manages the system state machine.
    """

    DRIFT_THRESHOLD = 80.0
    BREACH_THRESHOLD = 95.0

    def __init__(self, anchor_key: bytes) -> None:
        self.memory_pool = MemoryPool()
        self.rotator = EphemeralKeyRotator(anchor_key)
        self.sentry = HardenedSentry(self.rotator, self.memory_pool)
        self.foundry = FoundryModule()
        self.material_registry = MaterialRegistry()
        self.the_ancestry = TheAncestry()

        self.state: SystemState = SystemState.SYNCED
        self.symbiotic_phase_locks: list[str] = []
        self._state_history: list[dict[str, Any]] = []

    def evaluate_node_state(self, payload: dict[str, Any]) -> SystemState:
        """Evaluate a telemetry payload against thresholds and transition
        the system state machine accordingly."""
        sensor_value = payload.get("sensor_value", 0.0)
        previous_state = self.state

        if sensor_value >= self.BREACH_THRESHOLD:
            self.state = SystemState.STASIS_LOCKED
            self._break_phase_locks()
        elif sensor_value >= self.DRIFT_THRESHOLD:
            if self.state == SystemState.SYNCED:
                self.state = SystemState.DRIFT_LEVEL_1
            elif self.state == SystemState.DRIFT_LEVEL_1:
                self.state = SystemState.BREACH_LEVEL_2
                self._break_phase_locks()
        else:
            if self.state not in (SystemState.STASIS_LOCKED, SystemState.BREACH_LEVEL_2):
                self.state = SystemState.SYNCED

        if self.state != previous_state:
            self._state_history.append({
                "from": previous_state.value,
                "to": self.state.value,
                "at": time.time(),
                "trigger_value": sensor_value,
            })

        return self.state

    def _break_phase_locks(self) -> None:
        """Break all active symbiotic phase locks on breach."""
        self.symbiotic_phase_locks.clear()

    def get_state_snapshot(self) -> dict[str, Any]:
        """Return the current system state as a JSON-serializable dict."""
        return {
            "state": self.state.value,
            "live_stream_count": len(self.memory_pool.live_stream),
            "friction_count": len(self.memory_pool.friction_history),
            "spectral_footprints": len(self.memory_pool.spectral_footprints),
            "phase_locks": list(self.symbiotic_phase_locks),
            "recent_friction": self.memory_pool.friction_history[-10:],
            "state_history": self._state_history[-10:],
            "timestamp": time.time(),
        }


# ---------------------------------------------------------------------------
# NetworkGraftServer — FastAPI + WebSocket Engine
# ---------------------------------------------------------------------------

ANCHOR_KEY = os.environ.get("DTS_ANCHOR_KEY", "dts_default_anchor_2024").encode()

the_live = TheLive(anchor_key=ANCHOR_KEY)

app = FastAPI(title="Digital Twin Sanctuary — Network Graft Point")

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

ui_clients: set[WebSocket] = set()


@app.get("/")
async def serve_index() -> FileResponse:
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/api/state")
async def get_state() -> JSONResponse:
    return JSONResponse(the_live.get_state_snapshot())


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


async def broadcast_state() -> None:
    """Push current state snapshot to all connected UI clients."""
    snapshot = the_live.get_state_snapshot()
    message = json.dumps({"type": "STATE_UPDATE", **snapshot})
    disconnected: list[WebSocket] = []
    for ws in ui_clients:
        try:
            await ws.send_text(message)
        except Exception:
            disconnected.append(ws)
    for ws in disconnected:
        ui_clients.discard(ws)


@app.websocket("/graft")
async def graft_endpoint(websocket: WebSocket) -> None:
    """Primary WebSocket graft point for node connections and UI clients."""
    await websocket.accept()
    ui_clients.add(websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                packet = json.loads(raw)
            except json.JSONDecodeError:
                the_live.memory_pool.log_friction({
                    "type": "MALFORMED_PACKET",
                    "raw": raw[:200],
                })
                await websocket.send_text(json.dumps({
                    "status": "CIRCUIT_BREAK",
                    "reason": "Malformed JSON packet",
                }))
                break

            # --- Client identification ---
            if packet.get("type") == "UI_SUBSCRIBE":
                await websocket.send_text(json.dumps({
                    "type": "STATE_UPDATE",
                    **the_live.get_state_snapshot(),
                }))
                continue

            # --- HardenedSentry evaluation ---
            is_valid, reason = the_live.sentry.validate(packet)

            if not is_valid:
                await websocket.send_text(json.dumps({
                    "status": "CIRCUIT_BREAK",
                    "reason": reason,
                }))
                await broadcast_state()
                break  # structural circuit break — disconnect

            # --- Valid packet — ingest & evaluate ---
            payload = packet.get("payload", {})
            the_live.memory_pool.ingest(payload)
            new_state = the_live.evaluate_node_state(payload)

            await websocket.send_text(json.dumps({
                "status": "ACCEPTED",
                "state": new_state.value,
            }))
            await broadcast_state()

    except WebSocketDisconnect:
        pass
    finally:
        ui_clients.discard(websocket)


# ---------------------------------------------------------------------------
# Background Sequences
# ---------------------------------------------------------------------------

@app.on_event("startup")
async def start_background_sequences() -> None:
    asyncio.create_task(_telemetry_compression_loop())
    asyncio.create_task(_run_macro_mesh_server())


async def _telemetry_compression_loop() -> None:
    """Periodically run age_and_compress_telemetry every 60 seconds."""
    while True:
        await asyncio.sleep(60)
        age_and_compress_telemetry(the_live.memory_pool)


# ---------------------------------------------------------------------------
# Macro Mesh — P2P TCP Socket Server (:8899)
# ---------------------------------------------------------------------------

MACRO_MESH_HOST = "127.0.0.1"
MACRO_MESH_PORT = 8899


async def _handle_macro_mesh_client(
    reader: asyncio.StreamReader, writer: asyncio.StreamWriter
) -> None:
    """Handle a single Macro Mesh P2P TCP connection.

    Parses incoming newline-delimited JSON frames and dispatches:
      - RESONANCE_DEFICIT_BROADCAST  → MaterialRegistry
      - CROSS_ANCESTRY_AUDIT_REQUEST → TheAncestry
    """
    peer = writer.get_extra_info("peername")
    try:
        while True:
            data = await reader.readline()
            if not data:
                break

            try:
                frame = json.loads(data.decode().strip())
            except (json.JSONDecodeError, UnicodeDecodeError):
                the_live.memory_pool.log_friction({
                    "type": "MACRO_MESH_MALFORMED",
                    "peer": str(peer),
                    "raw": data[:200].decode(errors="replace"),
                })
                response = {"status": "ERROR", "reason": "Malformed frame"}
                writer.write((json.dumps(response) + "\n").encode())
                await writer.drain()
                continue

            frame_type = frame.get("type", "")

            if frame_type == "RESONANCE_DEFICIT_BROADCAST":
                the_live.material_registry.record_resonance_deficit(frame)
                the_live.the_ancestry.append_block({
                    "type": "RESONANCE_DEFICIT",
                    "source": frame.get("source", "unknown"),
                    "deficit": frame.get("deficit", {}),
                })
                response = {
                    "status": "DEFICIT_ACKNOWLEDGED",
                    "registry_snapshot": the_live.material_registry.get_registry_snapshot(),
                }
                writer.write((json.dumps(response) + "\n").encode())
                await writer.drain()

            elif frame_type == "CROSS_ANCESTRY_AUDIT_REQUEST":
                audit_response = the_live.the_ancestry.get_audit_response()
                writer.write((json.dumps(audit_response) + "\n").encode())
                await writer.drain()

            else:
                the_live.memory_pool.log_friction({
                    "type": "MACRO_MESH_UNKNOWN_FRAME",
                    "peer": str(peer),
                    "frame_type": frame_type,
                })
                response = {
                    "status": "ERROR",
                    "reason": f"Unknown frame type: {frame_type}",
                }
                writer.write((json.dumps(response) + "\n").encode())
                await writer.drain()

    except (ConnectionResetError, BrokenPipeError):
        pass
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass


async def _run_macro_mesh_server() -> None:
    """Start the Macro Mesh TCP server on :8899 concurrently with
    the main FastAPI/WebSocket server on :8888."""
    server = await asyncio.start_server(
        _handle_macro_mesh_client, MACRO_MESH_HOST, MACRO_MESH_PORT
    )
    async with server:
        await server.serve_forever()


# ---------------------------------------------------------------------------
# Entry Point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8888)
