// sim-runtime.mjs — Client API for the simulation SharedWorker
//
// Connects to js/sim-worker.mjs via SharedWorker + MessagePort.
// Exposes globalThis.simRuntime for both JS and PyScript to use.
//
// Usage:
//   await simRuntime.connect()
//   simRuntime.addPart(id, partDbId, connectors, buses)
//   simRuntime.addWire(id, from, fromConn, to, toConn)
//   simRuntime.runCode(source)

let worker = null
let port = null
let readyResolve = null
const readyPromise = new Promise(r => { readyResolve = r })

// Callbacks (set by PyScript or JS)
let onPinState = null
let onConflict = null
let onSerialOut = null
let onReady = null
let onError = null

const simRuntime = {
    ready: false,

    async connect() {
        if (worker) return
        worker = new SharedWorker('js/sim-worker.mjs', { type: 'module', name: 'breadboard-sim' })
        port = worker.port

        port.onmessage = (ev) => {
            const msg = ev.data
            switch (msg.type) {
                case 'ready':
                    simRuntime.ready = true
                    if (readyResolve) { readyResolve(); readyResolve = null }
                    if (onReady) onReady()
                    break
                case 'serial_out':
                    if (onSerialOut) onSerialOut(msg.data)
                    break
                case 'pin_state':
                    if (onPinState) onPinState(msg.changes)
                    break
                case 'conflict':
                    if (onConflict) onConflict(msg.conflicts)
                    break
                case 'error':
                    console.error('[sim]', msg.message)
                    if (onError) onError(msg.message)
                    break
            }
        }

        port.start()
        await readyPromise
    },

    // ---- Layout commands ----

    addPart(id, partDbId, connectors, buses) {
        port?.postMessage({ type: 'part_added', id, partDbId, connectors, buses })
    },

    removePart(id) {
        port?.postMessage({ type: 'part_removed', id })
    },

    addWire(id, from, fromConn, to, toConn) {
        port?.postMessage({ type: 'wire_added', id, from, fromConn, to, toConn })
    },

    removeWire(id) {
        port?.postMessage({ type: 'wire_removed', id })
    },

    bindMcu(id, pinMap) {
        port?.postMessage({ type: 'mcu_bind', id, pinMap })
    },

    // ---- Code execution ----

    runCode(source) {
        port?.postMessage({ type: 'run_code', source })
    },

    serialWrite(text) {
        port?.postMessage({ type: 'serial_in', data: text })
    },

    stop() {
        port?.postMessage({ type: 'stop' })
    },

    reset() {
        port?.postMessage({ type: 'reset' })
    },

    // ---- Callbacks ----

    setOnPinState(fn)  { onPinState = fn },
    setOnConflict(fn)  { onConflict = fn },
    setOnSerialOut(fn) { onSerialOut = fn },
    setOnReady(fn)     { onReady = fn },
    setOnError(fn)     { onError = fn },
}

globalThis.simRuntime = simRuntime
export default simRuntime
