# breadboard.ing

A static HTML page for laying out electronic parts on a breadboard, connecting them with wires, and sharing designs via URL.

Uses the [Fritzing](https://github.com/fritzing/fritzing-parts) and [Adafruit Fritzing Library](https://github.com/adafruit/Fritzing-Library) as source parts.

## Quick Start

```bash
python3 -m http.server 8080
# Open http://localhost:8080
```

No build step, no dependencies. Regenerate the parts index if the submodules change:

```bash
python3 index_parts.py
```

## Usage

### Sidebar — Browse & Add Parts
Three tabs: **Fritzing** (1794 core parts), **Contrib** (375), **Adafruit** (920).
- Click **+** on any part to add it to the center of the canvas
- **Drag** from the sidebar onto the canvas
- **Search** by name, tag, or property

### Canvas — Arrange
- **Drag** parts to move them — they snap to the 0.1" grid
- **Scroll** to zoom (centered on cursor)
- **Drag the background** to pan
- **Double-click** a part to edit its label
- **R** to rotate selected part 90°

### Wires — Connect
1. Click the **Wire** button (🔌) or press **W**
2. Click a connector pin (small invisible target on each part)
3. Click another connector pin to complete the wire
4. Press **S** or click **Select** to return to normal mode

### URL Sharing
All state (part positions, wires) is stored in the URL hash. Click **Share** to copy the link. Send it to anyone — they'll see the exact same layout when they open it.

### Shortcuts
| Key | Action |
|-----|--------|
| `S` | Select / drag mode |
| `W` | Wire drawing mode |
| `R` | Rotate selected part |
| `Delete` | Remove selected part |

## Architecture

```
├── index.html          ← The entire tool (self-contained static page)
├── index_parts.py      ← Scans submodules → parts_index.json
├── parts_index.json    ← Pre-generated parts database (~4.4 MB)
├── fritzing-parts/     ← Git submodule (github.com/fritzing/fritzing-parts)
├── adafruit-parts/     ← Git submodule (github.com/adafruit/Fritzing-Library)
└── .gitignore
```

### How SVGs are loaded
- **Fritzing parts** (.fzp): SVGs are loaded directly from `fritzing-parts/svg/{core|contrib}/{path}`
- **Adafruit parts** (.fzpz): SVGs are extracted from zip files on-the-fly client-side using [JSZip](https://stuk.github.io/jszip/)

### Coordinate System
- SVG coordinate system uses **100 units = 1 inch** (standard for Fritzing SVGs)
- **0.1" grid snap** = 10 SVG units (standard breadboard pitch)
- Display scale factor: 1.5 (SVG units → CSS pixels at 1× zoom)

### State Encoding
Layout state is JSON-serialized, base64-encoded, and stored in the URL hash fragment:
```
https://host/index.html#eyJwIjpbeyJpIjowLCJ4IjoyMCwieSI6...
```

## Regenerating the Index

When submodules are updated or when setting up fresh:

```bash
# Clone submodules if needed
git submodule update --init --recursive

# Scan parts and rebuild index
python3 index_parts.py
```
