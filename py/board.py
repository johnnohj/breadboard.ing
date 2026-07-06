"""
board.py - Bridge between breadboard layout (JS) and SharedWorker simulation

Runs in the main thread as <script type="mpy">.
Sends layout change messages to the SharedWorker via simRuntime.
Receives pin_state/serial_out messages and updates the DOM via animation.py.
"""

from js import document, window
import animation


def _rt():
    from js import simRuntime
    return simRuntime


# ---- Layout event handlers (called from JS via window.simBridge) ----

def on_part_placed(instance_id, part_db_id, connectors_json, buses_json):
    """Called by JS when a part is placed on the canvas."""
    from js import JSON
    connectors = list(JSON.parse(connectors_json))
    buses = list(JSON.parse(buses_json)) if buses_json else []
    bus_lists = [list(b) for b in buses] if buses else []

    _rt().addPart(instance_id, part_db_id, connectors, bus_lists)


def on_part_removed(instance_id):
    """Called by JS when a part is removed from the canvas."""
    animation.unregister_part(instance_id)
    _rt().removePart(instance_id)


def on_wire_added(wire_id, from_part, from_conn, to_part, to_conn):
    """Called by JS when a wire is connected."""
    _rt().addWire(wire_id, from_part, from_conn, to_part, to_conn)


def on_wire_removed(wire_id):
    """Called by JS when a wire is deleted."""
    _rt().removeWire(wire_id)


def on_mcu_bound(instance_id, pin_map_json):
    """Called by JS when a placed part is designated as the MCU."""
    from js import JSON
    pin_map = dict(JSON.parse(pin_map_json))
    _rt().bindMcu(instance_id, pin_map)


def on_code_run(source):
    """Called by JS when user clicks Run."""
    _rt().runCode(source)


def on_serial_input(text):
    """Called by JS when user types in the terminal."""
    _rt().serialWrite(text)


def on_stop():
    """Called by JS on Ctrl+C."""
    _rt().stop()


def on_reset():
    """Called by JS on Ctrl+D."""
    _rt().reset()


# ---- Incoming event handlers (from SharedWorker) ----

def _on_pin_state(changes):
    """Worker sent pin state changes — update visuals."""
    animation.apply_changes(changes)


def _on_serial_out(text):
    """Worker sent serial output — append to terminal."""
    term = document.getElementById('simTerminal')
    if term:
        term.textContent += text
        term.scrollTop = term.scrollHeight


def _on_conflict(conflicts):
    """Worker detected electrical conflicts."""
    # TODO: visual conflict indicators on wires/pins
    for c in conflicts:
        print(f"[sim] conflict on net {c.netId}: nodes {c.driverA} vs {c.driverB}")


def _on_ready():
    """Worker finished WASM init."""
    status = document.getElementById('simStatus')
    if status:
        status.textContent = 'Simulation ready'
        status.style.color = '#a6e3a1'
    bar = document.getElementById('simStatusBar')
    if bar:
        bar.textContent = 'Sim: ready'


def _on_error(message):
    """Worker reported an error."""
    status = document.getElementById('simStatus')
    if status:
        status.textContent = f'Error: {message}'
        status.style.color = '#f38ba8'


# ---- Initialization ----

async def init():
    """Connect to SharedWorker and wire up callbacks."""
    rt = _rt()

    # Register incoming event callbacks
    rt.setOnPinState(_on_pin_state)
    rt.setOnSerialOut(_on_serial_out)
    rt.setOnConflict(_on_conflict)
    rt.setOnReady(_on_ready)
    rt.setOnError(_on_error)

    # Connect to SharedWorker
    await rt.connect()

    # Export bridge functions for JS
    from js import Object
    bridge = Object.new()
    bridge.onPartPlaced = on_part_placed
    bridge.onPartRemoved = on_part_removed
    bridge.onWireAdded = on_wire_added
    bridge.onWireRemoved = on_wire_removed
    bridge.onMcuBound = on_mcu_bound
    bridge.onCodeRun = on_code_run
    bridge.onSerialInput = on_serial_input
    bridge.onStop = on_stop
    bridge.onReset = on_reset
    window.simBridge = bridge


# Auto-init when module loads
await init()
