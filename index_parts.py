#!/usr/bin/env python3
"""Scan Fritzing and Adafruit part libraries and generate a parts database.
No SVG cache - SVGs are loaded directly from the submodules."""

import json, os, zipfile, xml.etree.ElementTree as ET, hashlib, re

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "parts_index.json")
parts = []
seen = set()

def extract_ns(root):
    tag = root.tag
    return (tag.split('}')[0] + '}') if '{' in tag else ''

def title_to_group(title_p):
    """Derive a group from title/tags for parts without family."""
    if not isinstance(title_p, dict):
        return 'Other'
    title = title_p.get('title', '')
    tags = title_p.get('tags', [])
    source = title_p.get('source', '')
    
    if source == 'fritzing':
        if tags:
            return tags[0]
        return 'Other ICs'
    else:
        # Adafruit: derive from title
        t = title
        if t.lower().startswith('adafruit'):
            t = t[8:].strip()
        words = t.split()
        if not words:
            return 'Adafruit'
        group = words[0]
        group = group.strip("'").strip('"').rstrip(',').rstrip(':').rstrip(';')
        if group and (group[0].isdigit() or len(group) <= 3):
            if len(words) > 1:
                group = group + ' ' + words[1].strip("'").strip('"').rstrip(',').rstrip(':')
        elif group.lower() in ('a', 'an', 'the'):
            if len(words) > 1:
                group = words[1]
        return group or 'Adafruit'

def derive_group(p):
    """Derive a folder group name from part metadata."""
    if p['source'] == 'fritzing':
        fam = p.get('properties', {}).get('family', '')
        if fam:
            return fam
    return title_to_group(p)

def assign_groups(parts):
    """First pass: assign initial groups. Then consolidate singletons."""
    # First pass: assign raw groups
    for p in parts:
        p['group'] = derive_group(p)
    
    # Count group sizes
    counts = {}
    for p in parts:
        g = p['group']
        counts[g] = counts.get(g, 0) + 1
    
    # Consolidate only singleton groups (1 part) into broader categories
    # Groups with 2+ parts keep their identity
    for p in parts:
        original = p['group']
        if counts.get(original, 0) == 1:
            p['group'] = singleton_to_broad(original, p)
    
    final_counts = {}
    for p in parts:
        g = p['group']
        final_counts[g] = final_counts.get(g, 0) + 1
    
    print(f'  Groups: {len(counts)} initial → {len(final_counts)} after consolidation')
    return final_counts

def singleton_to_broad(original, part):
    """Map a singleton part to a broader category based on keywords."""
    g = original.lower().strip()
    title = part.get('title', '').lower()
    tags = [t.lower() for t in part.get('tags', [])]
    all_text = g + ' ' + title + ' ' + ' '.join(tags)
    
    broad_map = [
        ('microcontroller', 'Microcontrollers'),
        ('arduino', 'Microcontrollers'),
        ('raspberry pi', 'Computers'),
        ('picaxe', 'Microcontrollers'),
        ('beaglebone', 'Computers'),
        ('teensy', 'Microcontrollers'),
        ('netduino', 'Microcontrollers'),
        ('mbed', 'Microcontrollers'),
        ('propeller', 'Microcontrollers'),
        ('launchpad', 'Microcontrollers'),
        ('adafruit feather', 'Adafruit Feather'),
        ('feather', 'Adafruit Feather'),
        ('adafruit metro', 'Adafruit Metro'),
        ('metro', 'Adafruit Metro'),
        ('adafruit flora', 'Adafruit Flora'),
        ('flora', 'Adafruit Flora'),
        ('gemma', 'Adafruit Gemma'),
        ('itsybitsy', 'Adafruit ItsyBitsy'),
        ('qt py', 'Adafruit QT Py'),
        ('trinket', 'Adafruit Trinket'),
        ('picowbell', 'Adafruit PiCowbell'),
        ('featherwing', 'Adafruit FeatherWing'),
        ('neopixel', 'NeoPixels'),
        ('arcade', 'Arcade & Buttons'),
        ('resistor', 'Resistors'),
        ('capacitor', 'Capacitors'),
        ('inductor', 'Inductors'),
        ('diode', 'Diodes'),
        ('transistor', 'Transistors'),
        ('voltage regulator', 'Power - Regulators'),
        ('boost converter', 'Power - Converters'),
        ('buck converter', 'Power - Converters'),
        ('powerboost', 'Power - Converters'),
        ('battery', 'Power - Batteries'),
        ('lipo', 'Power - LiPo'),
        ('sensor', 'Sensors'),
        ('accelerometer', 'Sensors - Motion'),
        ('gyroscope', 'Sensors - Motion'),
        ('magnetometer', 'Sensors - Motion'),
        ('imu', 'Sensors - Motion'),
        ('temperature', 'Sensors - Temperature'),
        ('thermocouple', 'Sensors - Temperature'),
        ('humidity', 'Sensors - Environment'),
        ('pressure', 'Sensors - Environment'),
        ('barometric', 'Sensors - Environment'),
        ('gas sensor', 'Sensors - Environment'),
        ('light sensor', 'Sensors - Light'),
        ('color sensor', 'Sensors - Light'),
        ('gps', 'Sensors - GPS'),
        ('oled', 'Displays - OLED'),
        ('lcd', 'Displays - LCD'),
        ('display', 'Displays'),
        ('matrix', 'Displays - Matrix'),
        ('segment', 'Displays - Segment'),
        ('tft', 'Displays - TFT'),
        ('e-paper', 'Displays - E-Paper'),
        ('led', 'LEDs'),
        ('eeprom', 'ICs - Memory'),
        ('memory', 'ICs - Memory'),
        ('op-amp', 'ICs - Op-Amps'),
        ('op amp', 'ICs - Op-Amps'),
        ('logic ic', 'ICs - Logic'),
        ('audio', 'ICs - Audio'),
        ('adc', 'ICs - ADC/DAC'),
        ('dac', 'ICs - ADC/DAC'),
        ('bluetooth', 'Wireless - Bluetooth'),
        ('wifi', 'Wireless - WiFi'),
        ('rf', 'Wireless - RF'),
        ('xbee', 'Wireless - XBee'),
        ('cellular', 'Wireless - Cellular'),
        ('gsm', 'Wireless - Cellular'),
        ('motor driver', 'Motor Control'),
        ('motor', 'Motor Control'),
        ('stepper', 'Motor Control'),
        ('servo', 'Motor Control'),
        ('joystick', 'Input - Joysticks'),
        ('button', 'Input - Buttons'),
        ('pushbutton', 'Input - Buttons'),
        ('switch', 'Input - Switches'),
        ('potentiometer', 'Input - Potentiometers'),
        ('encoder', 'Input - Encoders'),
        ('connector', 'Connectors'),
        ('header', 'Connectors - Headers'),
        ('pin header', 'Connectors - Headers'),
        ('usb', 'Connectors - USB'),
        ('audio jack', 'Connectors - Audio'),
        ('rj45', 'Connectors - RJ45'),
        ('screw terminal', 'Connectors - Terminal'),
        ('terminal block', 'Connectors - Terminal'),
        ('fuse', 'Fuses / Protection'),
        ('relay', 'Relays'),
        ('crystal', 'Oscillators / Crystals'),
        ('oscillator', 'Oscillators / Crystals'),
        ('buzzer', 'Audio - Buzzers'),
        ('speaker', 'Audio - Speakers'),
        ('microphone', 'Audio - Microphones'),
        ('solenoid', 'Solenoids / Actuators'),
        ('transformer', 'Transformers'),
        ('peltier', 'Thermal'),
        ('heatsink', 'Thermal'),
        ('breadboard', 'Breadboards / Prototyping'),
        ('protoboard', 'Breadboards / Prototyping'),
        ('proto', 'Breadboards / Prototyping'),
        ('perma', 'Breadboards / Prototyping'),
        ('fpga', 'ICs - Logic'),
        ('voltage source', 'Power - Sources'),
        ('power supply', 'Power - Supplies'),
        ('powersupply', 'Power - Supplies'),
        ('piezo', 'Audio - Buzzers'),
        ('ldr', 'Sensors - Light'),
        ('thermistor', 'Sensors - Temperature'),
        ('rtc', 'Sensors - RTC'),
        ('real time clock', 'Sensors - RTC'),
        ('ds1307', 'Sensors - RTC'),
        ('ds3231', 'Sensors - RTC'),
        ('sparkfun', 'Sparkfun (Misc)'),
        ('ftdi', 'FTDI / USB-Serial'),
        ('uart', 'FTDI / USB-Serial'),
        ('usb serial', 'FTDI / USB-Serial'),
        ('alligator', 'Alligator / Test Leads'),
        ('steppa', 'Motor Control'),
        ('crickit', 'Motor Control'),
        ('touch sensor', 'Sensors - Touch'),
        ('capacitive', 'Sensors - Touch'),
        ('mosfet', 'Transistors'),
        ('fet_n', 'Transistors'),
        ('fet_p', 'Transistors'),
        ('vibration', 'Sensors - Vibration'),
        ('tilt', 'Sensors - Tilt'),
        ('pir', 'Sensors - Motion'),
        ('motion sensor', 'Sensors - Motion'),
        ('ultrasonic', 'Sensors - Distance'),
        ('distance', 'Sensors - Distance'),
        ('current sensor', 'Sensors - Current'),
        ('current', 'Sensors - Current'),
        ('hall effect', 'Sensors - Magnetic'),
        ('sound', 'Sensors - Sound'),
        ('analog', 'Input - Analog'),
        ('nfc', 'Wireless - NFC'),
        ('rfid', 'Wireless - RFID'),
        ('ethernet', 'Networking'),
        ('can bus', 'Networking - CAN'),
        ('midi', 'Audio - MIDI'),
        ('audio amplifier', 'Audio - Amplifiers'),
        ('amplifier', 'Audio - Amplifiers'),
        ('preamplifier', 'Audio - Amplifiers'),
        ('solenoid', 'Solenoids / Actuators'),
        ('vibration motor', 'Motor Control'),
        ('encoder', 'Input - Encoders'),
        ('rotary encoder', 'Input - Encoders'),
        ('led matrix', 'Displays - Matrix'),
        ('7-segment', 'Displays - Segment'),
        ('14-segment', 'Displays - Segment'),
        ('character display', 'Displays - Character'),
        ('graphics display', 'Displays - Graphics'),
        ('oled display', 'Displays - OLED'),
        ('tft display', 'Displays - TFT'),
        ('keypad', 'Input - Keypads'),
        ('joystick', 'Input - Joysticks'),
        ('trimpot', 'Input - Potentiometers'),
    ]
    for keyword, category in broad_map:
        if keyword in all_text:
            return category
    
    return 'Other / Misc'

def _apply_transform(pos, transform_str):
    """Apply an SVG transform matrix to a (x, y) position.
    Returns transformed (x, y). Supports matrix(a,b,c,d,e,f) only.
    """
    if not transform_str:
        return pos
    m = re.search(r'matrix\s*\(([^)]+)\)', transform_str)
    if not m:
        return pos
    # Split on commas or whitespace
    parts = re.split(r'[\s,]+', m.group(1).strip())
    parts = [float(x) for x in parts if x]
    if len(parts) != 6:
        return pos
    a, b, c, d, e, f = parts
    x, y = pos
    return (a * x + c * y + e, b * x + d * y + f)


def get_grid_spacing_svg(svg_content):
    """Return SVG units per 0.1" grid cell, following Fritzing's convention.
    Fritzing computes DPI = viewBox_width / physical_width,
    then grid_spacing = DPI / 10 (SVG units per 0.1").
    Handles width in inches ("in") or millimeters ("mm").
    Returns None when metadata is unavailable."""
    w_match = re.search(r'width="([\d.]+)in"', svg_content)
    w_mm_match = re.search(r'width="([\d.]+)mm"', svg_content)
    vb_match = re.search(r'viewBox="[\d.]+ [\d.]+ ([\d.]+) ([\d.]+)"', svg_content)
    if not vb_match:
        return None
    vb_w = float(vb_match.group(1))
    if w_match:
        phys_inches = float(w_match.group(1))
    elif w_mm_match:
        phys_inches = float(w_mm_match.group(1)) / 25.4
    else:
        return None
    dpi = vb_w / phys_inches
    return dpi / 10  # SVG units per 0.1"


def compute_grid_spacing_from_connectors(connector_positions):
    """Infer SVG units per 0.1" grid cell from connector positions.
    Finds the most common gap between adjacent connectors in the same row/column.
    Rounds positions to 4 decimal places to handle floating-point noise.
    Returns None when insufficient data."""
    positions = list(connector_positions.values())
    if len(positions) < 3:
        return None

    # Round coordinates to 4 decimal places to eliminate SVG float noise
    rounded = [{'x': round(pt['x'], 4), 'y': round(pt['y'], 4)} for pt in positions]

    # Group by Y (rounded to 1 decimal), find the row with most connectors
    from collections import defaultdict
    rows = defaultdict(list)
    for pt in rounded:
        ry = round(pt['y'], 1)
        rows[ry].append(pt['x'])

    best_row = max(rows.values(), key=lambda r: len(r))
    best_row.sort()

    if len(best_row) < 3:
        # Try columns instead
        cols = defaultdict(list)
        for pt in rounded:
            rx = round(pt['x'], 1)
            cols[rx].append(pt['y'])
        best_col = max(cols.values(), key=lambda r: len(r))
        best_col.sort()
        if len(best_col) < 3:
            return None
        gaps = [round(best_col[i + 1] - best_col[i], 2) for i in range(len(best_col) - 1)]
    else:
        gaps = [round(best_row[i + 1] - best_row[i], 2) for i in range(len(best_row) - 1)]

    if not gaps:
        return None
    # Find the most common gap
    from collections import Counter
    gap_counts = Counter(gaps)
    most_common_gap, count = gap_counts.most_common(1)[0]
    # Ensure it's a reasonable grid spacing (between 5 and 15 SVG units for 0.1")
    # Fritzing standard is 7.2 (72 DPI), Adafruit uses 9.0 (90 DPI), etc.
    if 4 < most_common_gap < 20:
        return most_common_gap
    return None


def compute_grid_snap_points(connectors, connector_positions, raw_positions=None, grid_spacing_svg=None):
    """For each connector, find all others that are grid-congruent (spacing a
    multiple of 0.1" grid cell). Uses raw (untransformed) positions when
    available, transformed positions otherwise.
    Returns a list of snap points, each as:
    {"anchor": connectorId, "onGrid": [connectorId, ...]}.
    Deduplicates by remainder to avoid identical alignments from different anchors."""
    if grid_spacing_svg is None or grid_spacing_svg <= 0:
        # Try to infer from connector positions
        inferred = compute_grid_spacing_from_connectors(connector_positions)
        if inferred:
            G = inferred
        else:
            # Default to 100 DPI (standard Fritzing convention) when unknown
            G = 10.0
    else:
        G = float(grid_spacing_svg)
    EPS = 0.02
    ids = [c['id'] for c in connectors]
    # Use transformed positions for grid check (they account for SVG transforms).
    # Raw positions are pre-transform and may be at a different scale.
    check_positions = connector_positions
    seen = set()
    points = []
    for i, aid in enumerate(ids):
        a = check_positions.get(aid)
        if not a:
            continue
        on_grid = [aid]
        has_pair = False
        for bid in ids:
            if bid == aid:
                continue
            b = check_positions.get(bid)
            if not b:
                continue
            dx = b['x'] - a['x']
            dy = b['y'] - a['y']
            # Require non-zero spacing (ignore coincident connectors or same pos)
            if abs(dx) < EPS and abs(dy) < EPS:
                continue
            # Round to avoid floating-point noise (e.g. 8.9999998 instead of 9.0)
            dx = round(dx, 4)
            dy = round(dy, 4)
            if abs(dx % G) < EPS and abs(dy % G) < EPS:
                has_pair = True
                if bid not in on_grid:
                    on_grid.append(bid)
        if not has_pair:
            continue
        # Deduplicate by remainder (rounded to avoid float noise)
        rem_x = round((-a['x']) % G, 4)
        rem_y = round((-a['y']) % G, 4)
        key = f'{rem_x},{rem_y}'
        if key in seen:
            continue
        seen.add(key)
        points.append({'anchor': aid, 'onGrid': on_grid})
    return points


def extract_svg_connector_positions(svg_content):
    """Parse SVG content and extract connector pin positions.
    Returns (positions, raw_positions) where positions have transforms applied
    and raw_positions have only the raw SVG coordinates (before transform).
    Both are dicts mapping connector_id -> {x, y} in SVG coordinates.
    Connector pins are SVG elements with id="connectorNNNpin"."""
    positions = {}
    raw_positions = {}
    
    # Match connector IDs with optional letters then digits: connectorA1pin, connectorZ30pin
    conn_id_re = r'connector([A-Za-z]?\d+)pin'
    
    # Find rect elements with connector id
    for match in re.finditer(
        r'<rect\s[^>]*id="(' + conn_id_re + r')"[^>]*>',
        svg_content
    ):
        element = match.group(0)
        full_id = match.group(1)
        cid = full_id.replace('pin', '')
        x_match = re.search(r'x="([\d.]+)"', element)
        y_match = re.search(r'y="([\d.]+)"', element)
        w_match = re.search(r'width="([\d.]+)"', element)
        h_match = re.search(r'height="([\d.]+)"', element)
        t_match = re.search(r'transform="([^"]+)"', element)
        if x_match and y_match:
            x = float(x_match.group(1))
            y = float(y_match.group(1))
            w = float(w_match.group(1)) / 2 if w_match else 0
            h = float(h_match.group(1)) / 2 if h_match else 0
            cx = x + w
            cy = y + h
            raw_positions[cid] = {'x': cx, 'y': cy}
            px, py = _apply_transform((cx, cy), t_match.group(1) if t_match else '')
            positions[cid] = {'x': px, 'y': py}
    
    # Find circle elements with connector id
    for match in re.finditer(
        r'<circle\s[^>]*id="(' + conn_id_re + r')"[^>]*>',
        svg_content
    ):
        element = match.group(0)
        full_id = match.group(1)
        cid = full_id.replace('pin', '')
        cx_match = re.search(r'cx="([\d.]+)"', element)
        cy_match = re.search(r'cy="([\d.]+)"', element)
        t_match = re.search(r'transform="([^"]+)"', element)
        if cx_match and cy_match:
            cx = float(cx_match.group(1))
            cy = float(cy_match.group(1))
            raw_positions[cid] = {'x': cx, 'y': cy}
            px, py = _apply_transform((cx, cy), t_match.group(1) if t_match else '')
            positions[cid] = {'x': px, 'y': py}
    
    # Find ellipse elements with connector id
    for match in re.finditer(
        r'<ellipse\s[^>]*id="(' + conn_id_re + r')"[^>]*>',
        svg_content
    ):
        element = match.group(0)
        full_id = match.group(1)
        cid = full_id.replace('pin', '')
        cx_match = re.search(r'cx="([\d.]+)"', element)
        cy_match = re.search(r'cy="([\d.]+)"', element)
        t_match = re.search(r'transform="([^"]+)"', element)
        if cx_match and cy_match:
            cx = float(cx_match.group(1))
            cy = float(cy_match.group(1))
            raw_positions[cid] = {'x': cx, 'y': cy}
            px, py = _apply_transform((cx, cy), t_match.group(1) if t_match else '')
            positions[cid] = {'x': px, 'y': py}
    
    return positions, raw_positions


def extract_buses(root, ns):
    """Parse the <buses> element from a Fritzing .fzp file.
    Returns a list of {"id": bus_id, "members": [connector_id, ...]}.
    Returns empty list when no buses exist."""
    buses = []
    for bus_elem in root.findall(f'{ns}buses/{ns}bus'):
        bus_id = bus_elem.get('id', '')
        members = []
        for member in bus_elem.findall(f'{ns}nodeMember'):
            cid = member.get('connectorId', '')
            if cid:
                members.append(cid)
        if bus_id and members:
            buses.append({'id': bus_id, 'members': members})
    return buses


def parse_fzp(fzp_path, source, category):
    """Parse a .fzp file from fritzing-parts."""
    try:
        tree = ET.parse(fzp_path)
        root = tree.getroot()
        ns = extract_ns(root)
        
        title = root.findtext(f'{ns}title', '')
        module_id = root.get('moduleId', '')
        
        props = {}
        for prop in root.findall(f'{ns}properties/{ns}property'):
            name = prop.get('name', '')
            text = prop.text or ''
            props[name] = text.strip()
        
        tags = [t.text for t in root.findall(f'{ns}tags/{ns}tag') if t.text]
        
        buses = extract_buses(root, ns)
        
        connectors = []
        for conn in root.findall(f'{ns}connectors/{ns}connector'):
            cid = conn.get('id', '')
            cname = conn.get('name', '')
            connectors.append({
                'id': cid,
                'name': cname,
                'type': conn.get('type', ''),
                'description': conn.findtext(f'{ns}description', ''),
            })
        
        # SVG references from views
        svg_refs = {}
        for view_name in ['iconView', 'breadboardView', 'schematicView', 'pcbView']:
            view = root.find(f'{ns}views/{ns}{view_name}')
            if view is not None:
                layers = view.find(f'{ns}layers')
                if layers is not None:
                    img = layers.get('image', '')
                    if img:
                        svg_refs[view_name.replace('View', '')] = img
        
        tax = root.findtext(f'{ns}taxonomy', '')
        
        conn_positions = {}
        raw_conn_positions = {}
        grid_spacing = None
        breadboard_ref = svg_refs.get('breadboard', '')
        if breadboard_ref:
            svg_path = os.path.join(BASE, 'fritzing-parts', 'svg', category, breadboard_ref)
            if os.path.exists(svg_path):
                try:
                    with open(svg_path, 'r') as f:
                        svg_content = f.read()
                    conn_positions, raw_conn_positions = extract_svg_connector_positions(svg_content)
                    grid_spacing = get_grid_spacing_svg(svg_content)
                except Exception as e:
                    print(f"    SVG pos error {svg_path}: {e}")
        
        # If no SVG-derived grid spacing, try from connector positions
        if grid_spacing is None:
            grid_spacing = compute_grid_spacing_from_connectors(conn_positions)
        
        result = {
            'id': module_id or hashlib.md5(fzp_path.encode()).hexdigest()[:12],
            'title': title or os.path.splitext(os.path.basename(fzp_path))[0],
            'source': source,
            'category': category,
            'type': 'fzp',
            'fzp_file': os.path.relpath(fzp_path, BASE),
            'svg_refs': svg_refs,
            'buses': buses,
            'connectors': connectors,
            'connector_positions': conn_positions,
            'raw_connector_positions': raw_conn_positions,
            'grid_snap_points': compute_grid_snap_points(connectors, conn_positions, raw_conn_positions, grid_spacing),
            'grid_spacing_svg': grid_spacing,
            'tags': tags,
            'properties': props,
            'taxonomy': tax,
        }
        return result
    except Exception as e:
        print(f"  Error {fzp_path}: {e}")
        return None


def parse_fzpz(fzpz_path, source, category):
    """Parse a .fzpz file (zip) from adafruit-parts."""
    try:
        with zipfile.ZipFile(fzpz_path, 'r') as zf:
            fzp_names = [n for n in zf.namelist() if n.endswith('.fzp')]
            if not fzp_names:
                return None
            fzp_data = zf.read(fzp_names[0])
            root = ET.fromstring(fzp_data)
            ns = extract_ns(root)
            
            title = root.findtext(f'{ns}title', '')
            module_id = root.get('moduleId', '')
            
            connectors = []
            for conn in root.findall(f'{ns}connectors/{ns}connector'):
                cid = conn.get('id', '')
                cname = conn.get('name', '')
                connectors.append({
                    'id': cid,
                    'name': cname,
                    'type': conn.get('type', ''),
                    'description': conn.findtext(f'{ns}description', ''),
                })
            
            tags = [t.text for t in root.findall(f'{ns}tags/{ns}tag') if t.text]
            
            buses = extract_buses(root, ns)
            
            svg_refs = {}
            for view_name in ['iconView', 'breadboardView', 'schematicView', 'pcbView']:
                view = root.find(f'{ns}views/{ns}{view_name}')
                if view is not None:
                    layers = view.find(f'{ns}layers')
                    if layers is not None:
                        img = layers.get('image', '')
                        if img:
                            svg_refs[view_name.replace('View', '')] = img
            
            svg_files = [n for n in zf.namelist() if n.endswith('.svg')]
            
            conn_positions = {}
            raw_conn_positions = {}
            grid_spacing = None
            breadboard_ref = svg_refs.get('breadboard', '')
            if breadboard_ref:
                bb_filename = breadboard_ref.split('/')[-1]
                for svg_name in svg_files:
                    if svg_name.endswith(bb_filename) or ('breadboard' in svg_name):
                        try:
                            svg_content = zf.read(svg_name).decode('utf-8')
                            conn_positions, raw_conn_positions = extract_svg_connector_positions(svg_content)
                            grid_spacing = get_grid_spacing_svg(svg_content)
                            if conn_positions:
                                break
                        except:
                            pass
            
            if not conn_positions:
                for svg_name in svg_files:
                    if 'breadboard' in svg_name:
                        try:
                            svg_content = zf.read(svg_name).decode('utf-8')
                            conn_positions, raw_conn_positions = extract_svg_connector_positions(svg_content)
                            grid_spacing = get_grid_spacing_svg(svg_content)
                            if conn_positions:
                                break
                        except:
                            pass
            
            # If no SVG-derived grid spacing, try from connector positions
            if grid_spacing is None:
                grid_spacing = compute_grid_spacing_from_connectors(conn_positions)
            
            result = {
                'id': module_id or hashlib.md5(fzpz_path.encode()).hexdigest()[:12],
                'title': title or os.path.splitext(os.path.basename(fzpz_path))[0],
                'source': source,
                'category': category,
                'type': 'fzpz',
                'fzpz_file': os.path.relpath(fzpz_path, BASE),
                'svg_refs': svg_refs,
                'svg_files': svg_files,
                'buses': buses,
                'connectors': connectors,
                'connector_positions': conn_positions,
                'raw_connector_positions': raw_conn_positions,
                'grid_snap_points': compute_grid_snap_points(connectors, conn_positions, raw_conn_positions, grid_spacing),
                'grid_spacing_svg': grid_spacing,
                'tags': tags,
                'properties': {},
                'taxonomy': '',
            }
            return result
    except Exception as e:
        print(f"  Error {fzpz_path}: {e}")
        return None

# Scan fritzing-parts
for cat in ['core', 'contrib']:
    print(f"Scanning fritzing-parts/{cat}...")
    d = os.path.join(BASE, 'fritzing-parts', cat)
    if os.path.isdir(d):
        for f in sorted(os.listdir(d)):
            if f.endswith('.fzp'):
                fp = os.path.join(d, f)
                if fp not in seen:
                    seen.add(fp)
                    p = parse_fzp(fp, 'fritzing', cat)
                    if p:
                        parts.append(p)

# Scan adafruit-parts
print("Scanning adafruit-parts...")
ada_dir = os.path.join(BASE, 'adafruit-parts', 'parts')
if os.path.isdir(ada_dir):
    for f in sorted(os.listdir(ada_dir)):
        if f.endswith('.fzpz'):
            fp = os.path.join(ada_dir, f)
            if fp not in seen:
                seen.add(fp)
                p = parse_fzpz(fp, 'adafruit', 'parts')
                if p:
                    parts.append(p)

# Deduplicate IDs: append _1, _2, etc. when moduleId collisions occur
id_counts = {}
for p in parts:
    pid = p['id']
    id_counts[pid] = id_counts.get(pid, 0) + 1
seen_ids = {}
for p in parts:
    pid = p['id']
    if id_counts[pid] > 1:
        seen_ids[pid] = seen_ids.get(pid, 0) + 1
        p['id'] = f"{pid}___{seen_ids[pid]}"

print(f"Indexed {len(parts)} parts")
group_counts = assign_groups(parts)
print(f"Groups: {len(group_counts)}")
for g, c in sorted(group_counts.items(), key=lambda x: -x[1])[:50]:
    print(f"  {g}: {c}")

with open(OUT, 'w') as f:
    json.dump(parts, f, separators=(',', ':'))
print(f"Index: {os.path.getsize(OUT)} bytes")
