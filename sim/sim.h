/*
 * sim.h - Electrical continuity simulation engine
 *
 * Net graph: nodes are connector pins, edges are wires + internal buses.
 * Provides flood-fill net discovery, voltage propagation, conflict detection.
 *
 * Compiled to WASM (wasi-sdk), called from JS/PyScript.
 */

#ifndef SIM_H
#define SIM_H

#include <stdint.h>
#include <stdbool.h>

/* Limits */
#define SIM_MAX_NODES  1024
#define SIM_MAX_EDGES  2048
#define SIM_MAX_BUSES  128
#define SIM_MAX_BUS_MEMBERS 32
#define SIM_MAX_NET    256

/* Pin direction (matches CircuitPython digitalio) */
typedef enum {
    SIM_DIR_DISCONNECTED = 0,
    SIM_DIR_INPUT  = 1,
    SIM_DIR_OUTPUT = 2,
} sim_direction_t;

/* Pull resistor */
typedef enum {
    SIM_PULL_NONE = 0,
    SIM_PULL_UP   = 1,
    SIM_PULL_DOWN = 2,
} sim_pull_t;

/* Voltage level */
typedef enum {
    SIM_LEVEL_FLOAT = 0,   /* Hi-Z / disconnected */
    SIM_LEVEL_LOW   = 1,
    SIM_LEVEL_HIGH  = 2,
    SIM_LEVEL_CONFLICT = 3, /* Multiple drivers disagree */
} sim_level_t;

/* Node: a single connector pin on a placed part */
typedef struct {
    uint16_t part_id;       /* which placed part instance */
    uint16_t connector_idx; /* connector index within part */
    sim_direction_t dir;
    sim_pull_t pull;
    sim_level_t driven;     /* level being driven (if output) */
    sim_level_t resolved;   /* resolved level after propagation */
    int16_t  net_id;        /* assigned net (-1 = unassigned) */
    bool     active;
} sim_node_t;

/* Edge: a wire connecting two nodes */
typedef struct {
    uint16_t node_a;
    uint16_t node_b;
    uint16_t wire_id;       /* external wire ID for removal */
    bool     active;
} sim_edge_t;

/* Bus: internal short between connectors (from Fritzing <buses>) */
typedef struct {
    uint16_t members[SIM_MAX_BUS_MEMBERS];
    uint8_t  count;
    bool     active;
} sim_bus_t;

/* Conflict report */
typedef struct {
    int16_t  net_id;
    uint16_t driver_a;      /* node IDs of conflicting drivers */
    uint16_t driver_b;
} sim_conflict_t;

/* State change report */
typedef struct {
    uint16_t node_id;
    sim_level_t old_level;
    sim_level_t new_level;
} sim_change_t;

/* ---- API (exported from WASM) ---- */

/* Initialize / reset the simulation */
void sim_init(void);

/* Add a node. Returns node_id or -1 on overflow. */
int32_t sim_add_node(uint16_t part_id, uint16_t connector_idx);

/* Remove a node (marks inactive, does not compact). */
void sim_remove_node(uint16_t node_id);

/* Add a wire edge between two nodes. Returns edge_id or -1. */
int32_t sim_add_edge(uint16_t node_a, uint16_t node_b, uint16_t wire_id);

/* Remove an edge by wire_id. */
void sim_remove_edge_by_wire(uint16_t wire_id);

/* Add a bus (internal short). Returns bus_id or -1.
 * members_ptr points to an array of node_ids, count = number of members. */
int32_t sim_add_bus(const uint16_t *members_ptr, uint8_t count);

/* Remove a bus. */
void sim_remove_bus(uint16_t bus_id);

/* Set pin electrical state. */
void sim_set_pin(uint16_t node_id, sim_direction_t dir,
                 sim_level_t driven, sim_pull_t pull);

/* Run one propagation tick. Returns number of nodes that changed. */
uint32_t sim_tick(void);

/* Get the resolved level for a node. */
sim_level_t sim_get_level(uint16_t node_id);

/* Get the net ID for a node (-1 if unassigned). */
int16_t sim_get_net(uint16_t node_id);

/* Get all nodes in the same net as node_id.
 * Writes to out_buf (max out_max entries). Returns count. */
uint32_t sim_get_net_nodes(uint16_t node_id, uint16_t *out_buf, uint32_t out_max);

/* Get conflict list. Returns count, writes to out_buf. */
uint32_t sim_get_conflicts(sim_conflict_t *out_buf, uint32_t out_max);

/* Get changed nodes since last tick. Returns count, writes to out_buf. */
uint32_t sim_get_changes(sim_change_t *out_buf, uint32_t out_max);

/* Query helpers */
uint32_t sim_node_count(void);
uint32_t sim_edge_count(void);

/* Shared memory accessors for JS/Python interop without malloc */
sim_node_t   *sim_get_node_ptr(uint16_t node_id);
sim_change_t *sim_get_change_buf(void);
sim_conflict_t *sim_get_conflict_buf(void);
uint16_t     *sim_get_net_buf(void);

#endif /* SIM_H */
