// sim-worker.mjs — SharedWorker: simulation hub
//
// Hosts sim.wasm + host.wasm + firmware.wasm.
// Connected pages communicate via MessagePort.

import { createJsffiBindings } from './proxy_js.mjs'
//
// Protocol (page → worker):
//   { type: 'part_added',   id, partDbId, connectors: [...], buses: [[...], ...] }
//   { type: 'part_removed', id }
//   { type: 'wire_added',   id, from, fromConn, to, toConn }
//   { type: 'wire_removed', id }
//   { type: 'mcu_bind',     id, pinMap: { D13: 'connector5', ... } }
//   { type: 'run_code',     source }
//   { type: 'serial_in',    data }  // string or byte array
//   { type: 'stop' }                // Ctrl+C
//   { type: 'reset' }               // Ctrl+D
//
// Protocol (worker → page):
//   { type: 'ready' }
//   { type: 'serial_out',   data }
//   { type: 'pin_state',    changes: [{ nodeId, partId, connectorIdx, level }, ...] }
//   { type: 'conflict',     conflicts: [{ netId, driverA, driverB }, ...] }
//   { type: 'error',        message }

const WASM_BASE = '../wasm/'

// ---- State ----
const ports = new Set()
let simInst = null    // sim.wasm
let hostInst = null   // host.wasm
let fwInst = null     // firmware.wasm

// Node bookkeeping (mirrors simulation.py, but in JS for SharedWorker)
const nodeMap = new Map()    // "partId:connId" → nodeId
const partNodes = new Map()  // partId → [nodeId, ...]
const wireEdges = new Map()  // wireId → edgeId

// MCU binding
let mcuPartId = null
const mcuPinMap = new Map()  // pinName → nodeId

// Serial
const serialInQueue = []

// ---- Broadcast to all connected pages ----
function broadcast(msg) {
    for (const p of ports) {
        try { p.postMessage(msg) } catch (e) { ports.delete(p) }
    }
}

// ---- WASI shim factory ----
function makeWasi(getInst) {
    return {
        args_get: () => 0,
        args_sizes_get: (a, b) => {
            const d = new DataView(getInst().exports.memory.buffer)
            d.setUint32(a, 0, true); d.setUint32(b, 0, true); return 0
        },
        environ_get: () => 0,
        environ_sizes_get: (a, b) => {
            const d = new DataView(getInst().exports.memory.buffer)
            d.setUint32(a, 0, true); d.setUint32(b, 0, true); return 0
        },
        clock_time_get: (id, prec, out) => {
            const d = new DataView(getInst().exports.memory.buffer)
            d.setBigUint64(out, BigInt(Math.floor(performance.now() * 1e6)), true)
            return 0
        },
        fd_close: () => 0, fd_seek: () => 0, fd_sync: () => 0,
        fd_fdstat_get: (fd, out) => {
            const d = new DataView(getInst().exports.memory.buffer)
            d.setUint8(out, 6); d.setUint16(out + 2, 0, true)
            d.setBigUint64(out + 8, 0n, true); d.setBigUint64(out + 16, 0n, true)
            return 0
        },
        fd_read: (fd, iovs, iovsLen, nread) => {
            const d = new DataView(getInst().exports.memory.buffer)
            if (fd === 0 && serialInQueue.length > 0) {
                const u = new Uint8Array(getInst().exports.memory.buffer)
                let total = 0
                for (let i = 0; i < iovsLen; i++) {
                    const ptr = d.getUint32(iovs + i * 8, true)
                    const len = d.getUint32(iovs + i * 8 + 4, true)
                    for (let j = 0; j < len && serialInQueue.length > 0; j++) {
                        u[ptr + j] = serialInQueue.shift()
                        total++
                    }
                }
                d.setUint32(nread, total, true)
                return 0
            }
            d.setUint32(nread, 0, true)
            return 0
        },
        fd_write: (fd, iovs, iovsLen, nw) => {
            const d = new DataView(getInst().exports.memory.buffer)
            const u = new Uint8Array(getInst().exports.memory.buffer)
            let total = 0
            let text = ''
            for (let i = 0; i < iovsLen; i++) {
                const ptr = d.getUint32(iovs + i * 8, true)
                const len = d.getUint32(iovs + i * 8 + 4, true)
                text += new TextDecoder().decode(u.slice(ptr, ptr + len))
                total += len
            }
            if ((fd === 1 || fd === 2) && text) {
                broadcast({ type: 'serial_out', data: text })
            }
            d.setUint32(nw, total, true)
            return 0
        },
        fd_prestat_get: () => 8, fd_prestat_dir_name: () => 8,
        path_create_directory: () => 44, path_filestat_get: () => 44,
        path_open: () => 44, path_readlink: () => 44,
        path_remove_directory: () => 44, path_rename: () => 44,
        path_unlink_file: () => 44, fd_readdir: () => 44,
        poll_oneoff: () => 0,
        proc_exit: (code) => { throw new Error(`proc_exit(${code})`) },
        sched_yield: () => 0,
        random_get: (buf, len) => {
            crypto.getRandomValues(new Uint8Array(getInst().exports.memory.buffer, buf, len))
            return 0
        },
    }
}

// ---- HAL imports for firmware ----
function makeHal() {
    return {
        notify_pin: (pin, value) => {
            // Firmware drove a pin — update sim and propagate
            const pinName = `D${pin}`
            const nid = mcuPinMap.get(pinName)
            if (nid !== undefined && simInst) {
                const dir = 2  // output
                const level = value ? 2 : 1  // high or low
                simInst.exports.sim_set_pin(nid, dir, level, 0)
                runTick()
            }
        },
        pump: () => 0,
        yield: () => {},
        flush_hw: () => {},
        i2c_request: () => -1,  // stub: no I2C peripherals yet
        spi_request: () => -1,  // stub: no SPI peripherals yet
        drain_inbox: (bufPtr, maxLen) => {
            if (!fwInst) return 0
            const buf = new Uint8Array(fwInst.exports.memory.buffer, bufPtr, maxLen)
            let pos = 0
            while (serialInQueue.length > 0 && pos + 3 < maxLen) {
                buf[pos++] = 1    // type: serial
                buf[pos++] = 1    // length
                buf[pos++] = serialInQueue.shift()
            }
            return pos
        },
    }
}

// ---- Simulation tick + change broadcast ----
function runTick() {
    if (!simInst) return
    const sim = simInst.exports
    const nChanges = sim.sim_tick()
    if (nChanges === 0) return

    // Read changes from sim memory
    const changeBuf = sim.sim_get_change_buf()
    const dv = new DataView(simInst.exports.memory.buffer)
    const changes = []
    // sim_change_t layout: u16 node_id, 2 bytes pad, u32 old_level, u32 new_level = 12 bytes
    for (let i = 0; i < nChanges; i++) {
        const off = changeBuf + i * 12
        const nodeId = dv.getUint16(off, true)
        const newLevel = dv.getUint32(off + 8, true)
        // Look up part info from node
        const nodePtr = sim.sim_get_node_ptr(nodeId)
        const partId = dv.getUint16(nodePtr, true)
        const connIdx = dv.getUint16(nodePtr + 2, true)
        changes.push({ nodeId, partId, connectorIdx: connIdx, level: newLevel })
    }
    broadcast({ type: 'pin_state', changes })

    // Check conflicts
    const conflictBuf = sim.sim_get_conflict_buf()
    // Read conflict_count by checking how many were produced
    // (sim_tick sets internal conflict_count; we can read from the buffer)
    // For now, just check if first entry looks valid
    const nConflicts = sim.sim_get_conflicts(conflictBuf, 64)
    if (nConflicts > 0) {
        const conflicts = []
        for (let i = 0; i < nConflicts; i++) {
            const off = conflictBuf + i * 6
            conflicts.push({
                netId: dv.getInt16(off, true),
                driverA: dv.getUint16(off + 2, true),
                driverB: dv.getUint16(off + 4, true),
            })
        }
        broadcast({ type: 'conflict', conflicts })
    }
}

// ---- Message handler ----
function handleMessage(msg, port) {
    const sim = simInst?.exports
    switch (msg.type) {
        case 'part_added': {
            const nodes = []
            for (let i = 0; i < msg.connectors.length; i++) {
                const cid = msg.connectors[i]
                const nid = sim.sim_add_node(msg.id, i)
                if (nid >= 0) {
                    nodeMap.set(`${msg.id}:${cid}`, nid)
                    nodes.push(nid)
                }
            }
            partNodes.set(msg.id, nodes)
            // Internal buses
            if (msg.buses) {
                for (const bus of msg.buses) {
                    const members = bus.map(cid => nodeMap.get(`${msg.id}:${cid}`))
                        .filter(n => n !== undefined)
                    if (members.length >= 2) {
                        // Connect all pairs via edges (bus)
                        for (let i = 1; i < members.length; i++) {
                            sim.sim_add_edge(members[0], members[i], 0xFFFF)
                        }
                    }
                }
            }
            break
        }
        case 'part_removed': {
            const nodes = partNodes.get(msg.id) || []
            for (const nid of nodes) sim.sim_remove_node(nid)
            partNodes.delete(msg.id)
            // Clean nodeMap
            for (const [key, nid] of nodeMap) {
                if (key.startsWith(`${msg.id}:`)) nodeMap.delete(key)
            }
            runTick()
            break
        }
        case 'wire_added': {
            const na = nodeMap.get(`${msg.from}:${msg.fromConn}`)
            const nb = nodeMap.get(`${msg.to}:${msg.toConn}`)
            if (na !== undefined && nb !== undefined) {
                // Use a numeric hash of the wire ID string
                const wireNum = hashWireId(msg.id)
                const eid = sim.sim_add_edge(na, nb, wireNum)
                if (eid >= 0) wireEdges.set(msg.id, wireNum)
                runTick()
            }
            break
        }
        case 'wire_removed': {
            const wireNum = wireEdges.get(msg.id)
            if (wireNum !== undefined) {
                sim.sim_remove_edge_by_wire(wireNum)
                wireEdges.delete(msg.id)
                runTick()
            }
            break
        }
        case 'mcu_bind': {
            mcuPartId = msg.id
            mcuPinMap.clear()
            for (const [pinName, cid] of Object.entries(msg.pinMap)) {
                const nid = nodeMap.get(`${msg.id}:${cid}`)
                if (nid !== undefined) mcuPinMap.set(pinName, nid)
            }
            break
        }
        case 'run_code': {
            if (!fwInst) {
                port.postMessage({ type: 'error', message: 'Firmware not loaded' })
                break
            }
            const enc = new TextEncoder().encode(msg.source)
            const ptr = fwInst.exports.malloc(enc.length + 1)
            const u8 = new Uint8Array(fwInst.exports.memory.buffer)
            u8.set(enc, ptr)
            u8[ptr + enc.length] = 0
            try {
                if (fwInst.exports.compile_and_run) {
                    fwInst.exports.compile_and_run(ptr, enc.length)
                } else if (fwInst.exports.mp_js_do_str) {
                    fwInst.exports.mp_js_do_str(ptr, enc.length)
                }
            } catch (e) {
                broadcast({ type: 'serial_out', data: `\nError: ${e.message}\n` })
            }
            fwInst.exports.free(ptr)
            break
        }
        case 'serial_in': {
            const bytes = typeof msg.data === 'string'
                ? Array.from(new TextEncoder().encode(msg.data))
                : Array.from(msg.data)
            serialInQueue.push(...bytes)
            break
        }
        case 'stop': {
            serialInQueue.push(0x03) // Ctrl+C
            break
        }
        case 'reset': {
            serialInQueue.push(0x04) // Ctrl+D
            break
        }
    }
}

function hashWireId(id) {
    // Simple string hash → u16 for sim edge wire_id
    let h = 0
    for (let i = 0; i < id.length; i++) {
        h = ((h << 5) - h + id.charCodeAt(i)) & 0xFFFF
    }
    return h || 1 // avoid 0 (reserved) and 0xFFFF (bus edges)
}

// ---- WASM loading ----
async function initWasm() {
    try {
        const [simResp, hostResp, fwResp] = await Promise.all([
            fetch(WASM_BASE + 'sim.wasm'),
            fetch(WASM_BASE + 'host.wasm'),
            fetch(WASM_BASE + 'firmware.wasm'),
        ])

        // sim.wasm
        const simMod = await WebAssembly.compile(await simResp.arrayBuffer())
        simInst = await WebAssembly.instantiate(simMod, {
            wasi_snapshot_preview1: makeWasi(() => simInst),
        })
        simInst.exports.sim_init()

        // host.wasm
        const hostMod = await WebAssembly.compile(await hostResp.arrayBuffer())
        hostInst = await WebAssembly.instantiate(hostMod, {
            wasi_snapshot_preview1: makeWasi(() => hostInst),
        })
        if (hostInst.exports._initialize) hostInst.exports._initialize()

        // firmware.wasm — needs jsffi + hal imports
        if (fwResp.ok) {
            const fwMod = await WebAssembly.compile(await fwResp.arrayBuffer())
            const jsffi = createJsffiBindings(
                () => fwInst.exports.memory,
                () => fwInst.exports,
            )
            fwInst = await WebAssembly.instantiate(fwMod, {
                wasi_snapshot_preview1: makeWasi(() => fwInst),
                wasi: { 'thread-spawn': () => { throw new Error('threads not supported') } },
                hal: makeHal(),
                jsffi,
            })
            if (fwInst.exports._initialize) fwInst.exports._initialize()
        }

        broadcast({ type: 'ready' })
    } catch (e) {
        broadcast({ type: 'error', message: `WASM init failed: ${e.message}` })
    }
}

// ---- SharedWorker connection handler ----
self.onconnect = (e) => {
    const port = e.ports[0]
    ports.add(port)

    port.onmessage = (ev) => handleMessage(ev.data, port)

    port.onmessageerror = () => ports.delete(port)

    // If already initialized, tell the new page
    if (simInst) {
        port.postMessage({ type: 'ready' })
    }

    port.start()
}

// Start loading WASM immediately
initWasm()
