"""
animation.py - Map simulation state changes to visual effects

Translates sim node level changes into DOM updates:
- LED glow (on/off/color)
- Pin state indicators (high/low/float/conflict)
- Signal flow visualization on wires
- NeoPixel color rendering
"""

from js import document


# Level enum matches sim.h
LEVEL_FLOAT    = 0
LEVEL_LOW      = 1
LEVEL_HIGH     = 2
LEVEL_CONFLICT = 3

# CSS classes/colors for each level
LEVEL_STYLES = {
    LEVEL_FLOAT:    {'color': 'transparent', 'cls': 'pin-float'},
    LEVEL_LOW:      {'color': '#4fc3f7',     'cls': 'pin-low'},
    LEVEL_HIGH:     {'color': '#f44336',     'cls': 'pin-high'},
    LEVEL_CONFLICT: {'color': '#ff9800',     'cls': 'pin-conflict'},
}

# Node-to-DOM element mapping (populated by board.py when parts are placed)
# Maps node_id -> { 'el': DOM element, 'part_id': int, 'connector': str, 'type': str }
_node_visuals = {}


def register_node_visual(node_id, part_instance_id, connector_id, element, visual_type='pin'):
    """Register a DOM element to animate for a sim node.

    Args:
        node_id: sim node ID
        part_instance_id: placed part instance ID
        connector_id: connector string ID
        element: DOM element (connector-pin div or LED element)
        visual_type: 'pin', 'led', 'neopixel'
    """
    _node_visuals[node_id] = {
        'el': element,
        'part_id': part_instance_id,
        'connector': connector_id,
        'type': visual_type,
    }


def unregister_part(part_instance_id):
    """Remove all visual registrations for a part."""
    to_remove = [nid for nid, v in _node_visuals.items()
                 if v['part_id'] == part_instance_id]
    for nid in to_remove:
        del _node_visuals[nid]


def apply_changes(changes):
    """Apply a list of simulation changes to the DOM.

    Args:
        changes: list of {nodeId, oldLevel, newLevel} from simRuntime
    """
    for ch in changes:
        node_id = ch['nodeId'] if isinstance(ch, dict) else ch.nodeId
        new_level = ch['newLevel'] if isinstance(ch, dict) else ch.newLevel
        _apply_node_level(node_id, new_level)


def _apply_node_level(node_id, level):
    """Update the visual for a single node."""
    vis = _node_visuals.get(node_id)
    if not vis:
        return

    el = vis['el']
    vtype = vis['type']
    style = LEVEL_STYLES.get(level, LEVEL_STYLES[LEVEL_FLOAT])

    if vtype == 'pin':
        _animate_pin(el, level, style)
    elif vtype == 'led':
        _animate_led(el, level, style)
    elif vtype == 'neopixel':
        _animate_neopixel(el, level, style)


def _animate_pin(el, level, style):
    """Animate a connector pin indicator."""
    # Remove old classes
    for s in LEVEL_STYLES.values():
        el.classList.remove(s['cls'])
    # Add new class
    el.classList.add(style['cls'])

    if level == LEVEL_HIGH:
        el.style.background = 'rgba(244, 67, 54, 0.5)'
        el.style.borderColor = 'rgba(244, 67, 54, 0.8)'
        el.style.boxShadow = '0 0 6px rgba(244, 67, 54, 0.5)'
    elif level == LEVEL_LOW:
        el.style.background = 'rgba(79, 195, 247, 0.5)'
        el.style.borderColor = 'rgba(79, 195, 247, 0.8)'
        el.style.boxShadow = '0 0 6px rgba(79, 195, 247, 0.5)'
    elif level == LEVEL_CONFLICT:
        el.style.background = 'rgba(255, 152, 0, 0.6)'
        el.style.borderColor = 'rgba(255, 152, 0, 0.9)'
        el.style.boxShadow = '0 0 8px rgba(255, 152, 0, 0.7)'
    else:
        el.style.background = ''
        el.style.borderColor = ''
        el.style.boxShadow = ''


def _animate_led(el, level, style):
    """Animate an LED element (glow on/off)."""
    if level == LEVEL_HIGH:
        el.classList.add('led-on')
        el.classList.remove('led-off')
        el.style.background = style['color']
        el.style.boxShadow = f'0 0 12px {style["color"]}, 0 0 24px {style["color"]}'
    else:
        el.classList.remove('led-on')
        el.classList.add('led-off')
        el.style.background = '#333'
        el.style.boxShadow = ''


def _animate_neopixel(el, level, style):
    """Animate a NeoPixel (full RGB control done separately via set_neopixel)."""
    # Level-based animation is just on/off; RGB comes from neopixel_write
    _animate_led(el, level, style)


def set_neopixel_color(el, r, g, b):
    """Set a NeoPixel element to a specific RGB color."""
    color = f'rgb({r},{g},{b})'
    el.style.background = color
    brightness = (r + g + b) / (3 * 255)
    if brightness > 0.1:
        el.style.boxShadow = f'0 0 {int(brightness * 16)}px {color}'
        el.classList.add('led-on')
        el.classList.remove('led-off')
    else:
        el.style.boxShadow = ''
        el.classList.remove('led-on')
        el.classList.add('led-off')


def highlight_net(node_id, sim_module):
    """Highlight all nodes in the same net as node_id (for debugging)."""
    # Get net nodes via sim
    # This would need sim_get_net_nodes exposed; for now, use tick results
    pass


def clear_all():
    """Clear all visual state."""
    for vis in _node_visuals.values():
        el = vis['el']
        for s in LEVEL_STYLES.values():
            el.classList.remove(s['cls'])
        el.style.background = ''
        el.style.borderColor = ''
        el.style.boxShadow = ''
    _node_visuals.clear()
