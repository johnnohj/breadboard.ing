"""
simulation.py - Simulation API reference

The simulation logic runs inside the SharedWorker (js/sim-worker.mjs).
This module documents the protocol and can be used as a Python-side
helper if MicroPython is later loaded inside the worker.

Protocol messages are documented in js/sim-worker.mjs.
"""

# Level constants (match sim.h)
LEVEL_FLOAT    = 0
LEVEL_LOW      = 1
LEVEL_HIGH     = 2
LEVEL_CONFLICT = 3

# Direction constants
DIR_DISCONNECTED = 0
DIR_INPUT  = 1
DIR_OUTPUT = 2

# Pull constants
PULL_NONE = 0
PULL_UP   = 1
PULL_DOWN = 2


def level_name(level):
    """Human-readable level name."""
    return {
        LEVEL_FLOAT: 'float',
        LEVEL_LOW: 'LOW',
        LEVEL_HIGH: 'HIGH',
        LEVEL_CONFLICT: 'CONFLICT',
    }.get(level, f'?{level}')
