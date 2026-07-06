"""
url_state.py - URL encode/decode for board layout + code

Layout state (parts, positions, wires) goes in the URL hash.
Code is optionally included as gzipped base64.

Format: #parts=<encoded>&wires=<encoded>&code=<gzb64>
"""

import json
from js import window, encodeURIComponent, decodeURIComponent

# Compact encoding: parts as positional arrays, wires as edge lists
# This mirrors the existing JS URL encoding in index.html


def encode_state(parts, wires, code=None):
    """Encode layout state to a URL hash string.

    Args:
        parts: list of {id, partId, x, y, rotation, displayScale}
        wires: list of {id, fromPart, fromConn, toPart, toConn, color, curve}
        code: optional Python source code string

    Returns: hash string (without leading #)
    """
    # Parts: compact array encoding
    p_data = []
    for p in parts:
        p_data.append([
            p.get('partId', ''),
            round(p.get('x', 0), 1),
            round(p.get('y', 0), 1),
            p.get('rotation', 0),
        ])

    # Wires: edge list with metadata
    w_data = []
    for w in wires:
        entry = [
            w.get('fromPart', 0),
            w.get('fromConn', ''),
            w.get('toPart', 0),
            w.get('toConn', ''),
        ]
        color = w.get('color', '')
        curve = w.get('curve')
        if color or curve:
            entry.append(color)
        if curve:
            entry.append(round(curve.get('x', 0), 1))
            entry.append(round(curve.get('y', 0), 1))
        w_data.append(entry)

    state = {'p': p_data, 'w': w_data}

    encoded = encodeURIComponent(json.dumps(state, separators=(',', ':')))

    if code and len(code.strip()) > 0:
        # Include code as base64 (no gzip in MicroPython stdlib)
        from js import btoa
        code_b64 = btoa(code)
        return f'{encoded}&code={code_b64}'

    return encoded


def decode_state(hash_str):
    """Decode layout state from a URL hash string.

    Returns: (parts, wires, code) or (None, None, None) on error.
    """
    if not hash_str or hash_str == '':
        return None, None, None

    # Split off code parameter
    code = None
    main_str = hash_str
    if '&code=' in hash_str:
        idx = hash_str.index('&code=')
        main_str = hash_str[:idx]
        code_b64 = hash_str[idx + 6:]
        try:
            from js import atob
            code = atob(code_b64)
        except Exception:
            pass

    try:
        decoded = decodeURIComponent(main_str)
        state = json.loads(decoded)
    except Exception:
        return None, None, None

    parts = []
    for p in state.get('p', []):
        if len(p) >= 3:
            parts.append({
                'partId': p[0],
                'x': p[1],
                'y': p[2],
                'rotation': p[3] if len(p) > 3 else 0,
            })

    wires = []
    for w in state.get('w', []):
        if len(w) >= 4:
            wire = {
                'fromPart': w[0],
                'fromConn': w[1],
                'toPart': w[2],
                'toConn': w[3],
            }
            if len(w) > 4:
                wire['color'] = w[4]
            if len(w) > 6:
                wire['curve'] = {'x': w[5], 'y': w[6]}
            wires.append(wire)

    return parts, wires, code


def save_to_url(parts, wires, code=None):
    """Update the browser URL with the current state."""
    hash_str = encode_state(parts, wires, code)
    window.location.hash = hash_str


def load_from_url():
    """Load state from the current browser URL."""
    hash_str = window.location.hash
    if hash_str and hash_str.startswith('#'):
        hash_str = hash_str[1:]
    return decode_state(hash_str)
