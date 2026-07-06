// proxy_js.mjs — JS-side proxy bridge for jsffi
//
// Adapted from MicroPython ports/webassembly/proxy_js.js
// Replaces Emscripten's Module.ccall/getValue/setValue with direct
// WASM memory access via DataView.
//
// Usage: import { createJsffiBindings } from './proxy_js.mjs'
//   const jsffi = createJsffiBindings(wasmMemory, wasmExports)
//   // Pass jsffi as the 'jsffi' import namespace at instantiation

// PVN = 3 × u32 (kind, arg0, arg1)
const PVN = 3;

// PROXY_KIND constants (must match proxy_c.h)
const MP_EXCEPTION = -1;
const MP_NULL = 0;
const MP_NONE = 1;
const MP_BOOL = 2;
const MP_INT = 3;
const MP_FLOAT = 4;
const MP_STR = 5;
const MP_CALLABLE = 6;
const MP_GENERATOR = 7;
const MP_OBJECT = 8;
const MP_JSPROXY = 9;
const MP_EXISTING = 10;

const JS_UNDEFINED = 0;
const JS_NULL = 1;
const JS_BOOLEAN = 2;
const JS_INTEGER = 3;
const JS_DOUBLE = 4;
const JS_STRING = 5;
const JS_OBJECT_EXISTING = 6;
const JS_OBJECT = 7;
const JS_PYPROXY = 8;

class PythonError extends Error {
    constructor(type, details) {
        super(details);
        this.name = 'PythonError';
        this.type = type;
    }
}

export function createJsffiBindings(getMemory, getExports) {
    // JS object reference table
    // [0] = globalThis, [1] = undefined (sentinel)
    const jsRef = [globalThis, undefined];
    let jsRefNext = 2;
    const jsRefMap = new Map([[globalThis, 0]]);
    const jsExisting = [undefined];

    // PyProxy weak ref tracking
    const pyProxyMap = new Map();
    const pyProxyRegistry = new FinalizationRegistry((cRef) => {
        pyProxyMap.delete(cRef);
        try { getExports().proxy_c_free_obj(cRef); } catch (e) {}
    });

    // Memory helpers
    function dv() { return new DataView(getMemory().buffer); }
    function u8() { return new Uint8Array(getMemory().buffer); }

    function getI32(ptr) { return dv().getInt32(ptr, true); }
    function getU32(ptr) { return dv().getUint32(ptr, true); }
    function setI32(ptr, v) { dv().setInt32(ptr, v, true); }
    function setU32(ptr, v) { dv().setUint32(ptr, v, true); }

    function readStr(ptr, len) {
        return new TextDecoder().decode(u8().slice(ptr, ptr + len));
    }

    function writeStr(str) {
        const encoded = new TextEncoder().encode(str);
        const ptr = getExports().port_malloc(encoded.length + 1);
        u8().set(encoded, ptr);
        u8()[ptr + encoded.length] = 0;
        return { ptr, len: encoded.length };
    }

    // Add JS object to reference table, return its ID
    function addJsRef(obj) {
        if (obj === undefined) return 1;
        const existing = jsRefMap.get(obj);
        if (existing !== undefined) return existing;

        // Find free slot
        while (jsRefNext < jsRef.length) {
            if (jsRef[jsRefNext] === undefined) {
                const id = jsRefNext++;
                jsRef[id] = obj;
                jsRefMap.set(obj, id);
                return id;
            }
            jsRefNext++;
        }
        // Append
        const id = jsRef.length;
        jsRef.push(obj);
        jsRefNext = jsRef.length;
        jsRefMap.set(obj, id);
        return id;
    }

    // Convert JS value → PVN (write 3 × u32 at outPtr)
    function jsToPvn(jsObj, outPtr) {
        let kind;
        if (jsObj === undefined) {
            kind = JS_UNDEFINED;
        } else if (jsObj === null) {
            kind = JS_NULL;
        } else if (typeof jsObj === 'boolean') {
            kind = JS_BOOLEAN;
            setI32(outPtr + 4, jsObj ? 1 : 0);
        } else if (typeof jsObj === 'number') {
            if (Number.isInteger(jsObj) && jsObj >= -2147483648 && jsObj <= 2147483647) {
                kind = JS_INTEGER;
                setI32(outPtr + 4, jsObj);
            } else {
                kind = JS_DOUBLE;
                // Store double as two i32s
                const buf = new ArrayBuffer(8);
                new Float64Array(buf)[0] = jsObj;
                const view = new Int32Array(buf);
                setI32(outPtr + 4, view[0]);
                setI32(outPtr + 8, view[1]);
            }
        } else if (typeof jsObj === 'string') {
            kind = JS_STRING;
            const { ptr, len } = writeStr(jsObj);
            setI32(outPtr + 4, len);
            setI32(outPtr + 8, ptr);
        } else if (jsObj instanceof PyProxy || (typeof jsObj === 'function' && '_ref' in jsObj)) {
            kind = JS_PYPROXY;
            setI32(outPtr + 4, jsObj._ref);
        } else {
            const existingRef = jsRefMap.get(jsObj);
            if (existingRef !== undefined) {
                kind = JS_OBJECT_EXISTING;
                setI32(outPtr + 4, existingRef);
            } else {
                kind = JS_OBJECT;
                setI32(outPtr + 4, addJsRef(jsObj));
            }
        }
        setI32(outPtr, kind);
    }

    // Convert PVN (read 3 × u32 at ptr) → JS value
    function pvnToJs(ptr) {
        const kind = getI32(ptr);
        if (kind === MP_EXCEPTION) {
            const strLen = getI32(ptr + 4);
            const strPtr = getI32(ptr + 8);
            const str = readStr(strPtr, strLen);
            getExports().port_free(strPtr);
            const parts = str.split('\x04');
            throw new PythonError(parts[0], parts[1] || parts[0]);
        }
        if (kind === MP_NULL) throw new Error('MP_OBJ_NULL');
        if (kind === MP_NONE) return undefined;
        if (kind === MP_BOOL) return getI32(ptr + 4) !== 0;
        if (kind === MP_INT) return getI32(ptr + 4);
        if (kind === MP_FLOAT) {
            const buf = new ArrayBuffer(8);
            const view = new Int32Array(buf);
            view[0] = getI32(ptr + 4);
            view[1] = getI32(ptr + 8);
            return new Float64Array(buf)[0];
        }
        if (kind === MP_STR) {
            const len = getI32(ptr + 4);
            const p = getI32(ptr + 8);
            return readStr(p, len);
        }
        if (kind === MP_JSPROXY) {
            const id = getI32(ptr + 4);
            return jsRef[id];
        }
        if (kind === MP_EXISTING) {
            const id = getI32(ptr + 4);
            const obj = jsExisting[id];
            jsExisting[id] = undefined;
            return obj;
        }
        // MP_CALLABLE, MP_GENERATOR, MP_OBJECT
        const id = getI32(ptr + 4);
        let obj;
        if (kind === MP_CALLABLE) {
            obj = (...args) => callPython(id, args);
            obj._ref = id;
        } else if (kind === MP_GENERATOR) {
            obj = new PyProxyThenable(id);
        } else {
            obj = new Proxy(new PyProxy(id), pyProxyHandler);
        }
        pyProxyRegistry.register(obj, id);
        pyProxyMap.set(id, new WeakRef(obj));
        return obj;
    }

    function pvnToJsAndFree(ptr) {
        const ret = pvnToJs(ptr);
        getExports().port_free(ptr);
        return ret;
    }

    // Call a Python callable from JS
    function callPython(cRef, args) {
        // Strip trailing undefined
        while (args.length > 0 && args[args.length - 1] === undefined) args.pop();

        let argsPtr = 0;
        if (args.length > 0) {
            argsPtr = getExports().port_malloc(args.length * PVN * 4);
            for (let i = 0; i < args.length; i++) {
                jsToPvn(args[i], argsPtr + i * PVN * 4);
            }
        }
        const valuePtr = getExports().port_malloc(PVN * 4);
        getExports().proxy_c_to_js_call(cRef, args.length, argsPtr, valuePtr);
        if (argsPtr) getExports().port_free(argsPtr);
        return pvnToJsAndFree(valuePtr);
    }

    // PyProxy — wraps a Python object reference for JS access
    class PyProxy {
        constructor(ref) { this._ref = ref; }
    }

    class PyProxyThenable extends PyProxy {
        then(resolve, reject) {
            // TODO: async/await bridge
            resolve(this);
        }
    }

    const pyProxyHandler = {
        get(target, prop) {
            if (prop === '_ref') return target._ref;
            if (prop === 'then') return undefined;
            if (typeof prop === 'symbol') return undefined;

            const valuePtr = getExports().port_malloc(PVN * 4);
            const { ptr: namePtr, len: nameLen } = writeStr(String(prop));
            getExports().proxy_c_to_js_lookup_attr(target._ref, namePtr, nameLen, valuePtr);
            getExports().port_free(namePtr);
            try {
                return pvnToJsAndFree(valuePtr);
            } catch (e) {
                if (e instanceof PythonError && e.type === 'AttributeError') {
                    return undefined;
                }
                throw e;
            }
        },
        set(target, prop, value) {
            const pvnPtr = getExports().port_malloc(PVN * 4);
            jsToPvn(value, pvnPtr);
            const { ptr: namePtr, len: nameLen } = writeStr(String(prop));
            getExports().proxy_c_to_js_store_attr(target._ref, namePtr, nameLen, pvnPtr);
            getExports().port_free(namePtr);
            getExports().port_free(pvnPtr);
            return true;
        },
        has(target, prop) {
            if (typeof prop === 'symbol') return false;
            const { ptr: namePtr, len: nameLen } = writeStr(String(prop));
            const result = getExports().proxy_c_to_js_has_attr(target._ref, namePtr, nameLen);
            getExports().port_free(namePtr);
            return result !== 0;
        },
        apply(target, thisArg, args) {
            return callPython(target._ref, args);
        },
    };

    // ---- jsffi import implementations ----
    // These are called by WASM (from C proxy_c.c / objjsproxy.c)

    return {
        has_attr(jsref, strPtr, strLen) {
            const attr = readStr(strPtr, strLen);
            const obj = jsRef[jsref];
            return obj !== undefined && obj !== null && attr in Object(obj);
        },

        lookup_attr(jsref, strPtr, strLen, outPtr) {
            const attr = readStr(strPtr, strLen);
            const obj = jsRef[jsref];
            try {
                const val = obj[attr];
                jsToPvn(val, outPtr);
                if (typeof val === 'function') return 2;
                return val !== undefined ? 1 : 0;
            } catch (e) {
                jsToPvn(undefined, outPtr);
                return 0;
            }
        },

        store_attr(jsref, strPtr, strLen, valuePtr) {
            const attr = readStr(strPtr, strLen);
            const obj = jsRef[jsref];
            const val = pvnToJs(valuePtr);
            obj[attr] = val;
        },

        call0(jsref, outPtr) {
            try {
                const result = jsRef[jsref]();
                jsToPvn(result, outPtr);
            } catch (e) {
                jsToPvn(undefined, outPtr);
            }
        },

        call1(jsref, viaCall, argPtr, outPtr) {
            try {
                const arg = pvnToJs(argPtr);
                const fn = jsRef[jsref];
                // viaCall: arg is 'this' context, call with no args
                const result = viaCall ? fn.call(arg) : fn(arg);
                jsToPvn(result, outPtr);
                return 0;
            } catch (e) {
                jsToPvn(undefined, outPtr);
                return -1;
            }
        },

        calln(jsref, viaCall, nArgs, argsPtr, outPtr) {
            try {
                const args = [];
                for (let i = 0; i < nArgs; i++) {
                    args.push(pvnToJs(argsPtr + i * PVN * 4));
                }
                const fn = jsRef[jsref];
                // viaCall: first arg is 'this' context (bound method)
                const result = viaCall ? fn.call(args[0], ...args.slice(1)) : fn(...args);
                jsToPvn(result, outPtr);
                return 0;
            } catch (e) {
                jsToPvn(undefined, outPtr);
                return -1;
            }
        },

        calln_kw(jsref, viaCall, nArgs, argsPtr, nKw, kwKeysPtr, kwValsPtr, outPtr) {
            // KW args not commonly used in JS — treat as positional
            return this.calln(jsref, viaCall, nArgs, argsPtr, outPtr);
        },

        reflect_construct(jsref, nArgs, argsPtr, outPtr) {
            try {
                const args = [];
                for (let i = 0; i < nArgs; i++) {
                    args.push(pvnToJs(argsPtr + i * PVN * 4));
                }
                const result = Reflect.construct(jsRef[jsref], args);
                jsToPvn(result, outPtr);
            } catch (e) {
                jsToPvn(undefined, outPtr);
            }
        },

        get_iter(jsref, outPtr) {
            try {
                const iter = jsRef[jsref][Symbol.iterator]();
                jsToPvn(iter, outPtr);
            } catch (e) {
                jsToPvn(undefined, outPtr);
            }
        },

        iter_next(jsref, outPtr) {
            try {
                const { value, done } = jsRef[jsref].next();
                if (done) return 0;
                jsToPvn(value, outPtr);
                return 1;
            } catch (e) {
                return 0;
            }
        },

        subscr_load(jsref, indexPtr, outPtr) {
            try {
                const index = pvnToJs(indexPtr);
                const val = jsRef[jsref][index];
                jsToPvn(val, outPtr);
            } catch (e) {
                jsToPvn(undefined, outPtr);
            }
        },

        subscr_store(jsref, indexPtr, valuePtr) {
            try {
                const index = pvnToJs(indexPtr);
                const val = pvnToJs(valuePtr);
                jsRef[jsref][index] = val;
            } catch (e) {}
        },

        free_ref(jsref) {
            if (jsref >= 2 && jsref < jsRef.length) {
                const obj = jsRef[jsref];
                jsRef[jsref] = undefined;
                if (obj !== undefined) jsRefMap.delete(obj);
                if (jsref < jsRefNext) jsRefNext = jsref;
            }
        },

        check_existing(cRef) {
            const existing = pyProxyMap.get(cRef)?.deref();
            if (existing === undefined) return -1;
            for (let i = 0; i < jsExisting.length; i++) {
                if (jsExisting[i] === undefined) {
                    jsExisting[i] = existing;
                    return i;
                }
            }
            jsExisting.push(existing);
            return jsExisting.length - 1;
        },

        create_pyproxy(inOutPtr) {
            const cRef = getI32(inOutPtr + 4);
            const proxy = new Proxy(new PyProxy(cRef), pyProxyHandler);
            pyProxyRegistry.register(proxy, cRef);
            pyProxyMap.set(cRef, new WeakRef(proxy));
            const id = addJsRef(proxy);
            setI32(inOutPtr, JS_OBJECT);
            setI32(inOutPtr + 4, id);
        },

        to_js(inOutPtr) {
            const val = pvnToJs(inOutPtr);
            const id = addJsRef(val);
            setI32(inOutPtr, JS_OBJECT);
            setI32(inOutPtr + 4, id);
        },

        // Expose internals for _hal integration
        _jsRef: jsRef,
        _addJsRef: addJsRef,
        _pvnToJs: pvnToJs,
        _jsToPvn: jsToPvn,
        _callPython: callPython,
    };
}
