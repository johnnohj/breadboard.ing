/*
 * sim.c - Electrical continuity simulation engine
 *
 * Flood-fill net assignment, voltage propagation, conflict detection.
 * Statically allocated - no malloc needed in the hot path.
 */

#include "sim.h"
#include <string.h>

/* ---- Static state ---- */

static sim_node_t     nodes[SIM_MAX_NODES];
static sim_edge_t     edges[SIM_MAX_EDGES];
static sim_bus_t      buses[SIM_MAX_BUSES];
static uint32_t       node_count;
static uint32_t       edge_count;
static uint32_t       bus_count;

/* Scratch buffers for query results (shared with JS via pointer) */
static sim_change_t   change_buf[SIM_MAX_NODES];
static uint32_t       change_count;
static sim_conflict_t conflict_buf[SIM_MAX_NODES];
static uint32_t       conflict_count;
static uint16_t       net_buf[SIM_MAX_NET];

/* BFS queue for flood fill */
static uint16_t       bfs_queue[SIM_MAX_NODES];
static bool           bfs_visited[SIM_MAX_NODES];

/* ---- Init ---- */

void sim_init(void) {
    memset(nodes, 0, sizeof(nodes));
    memset(edges, 0, sizeof(edges));
    memset(buses, 0, sizeof(buses));
    node_count = 0;
    edge_count = 0;
    bus_count = 0;
    change_count = 0;
    conflict_count = 0;
}

/* ---- Node management ---- */

int32_t sim_add_node(uint16_t part_id, uint16_t connector_idx) {
    /* Find first inactive slot, or append */
    for (uint32_t i = 0; i < node_count; i++) {
        if (!nodes[i].active) {
            nodes[i] = (sim_node_t){
                .part_id = part_id,
                .connector_idx = connector_idx,
                .dir = SIM_DIR_DISCONNECTED,
                .pull = SIM_PULL_NONE,
                .driven = SIM_LEVEL_FLOAT,
                .resolved = SIM_LEVEL_FLOAT,
                .net_id = -1,
                .active = true,
            };
            return (int32_t)i;
        }
    }
    if (node_count >= SIM_MAX_NODES) return -1;
    uint32_t id = node_count++;
    nodes[id] = (sim_node_t){
        .part_id = part_id,
        .connector_idx = connector_idx,
        .dir = SIM_DIR_DISCONNECTED,
        .pull = SIM_PULL_NONE,
        .driven = SIM_LEVEL_FLOAT,
        .resolved = SIM_LEVEL_FLOAT,
        .net_id = -1,
        .active = true,
    };
    return (int32_t)id;
}

void sim_remove_node(uint16_t node_id) {
    if (node_id < SIM_MAX_NODES) {
        nodes[node_id].active = false;
    }
}

/* ---- Edge management ---- */

int32_t sim_add_edge(uint16_t node_a, uint16_t node_b, uint16_t wire_id) {
    /* Reuse inactive slot */
    for (uint32_t i = 0; i < edge_count; i++) {
        if (!edges[i].active) {
            edges[i] = (sim_edge_t){
                .node_a = node_a, .node_b = node_b,
                .wire_id = wire_id, .active = true,
            };
            return (int32_t)i;
        }
    }
    if (edge_count >= SIM_MAX_EDGES) return -1;
    uint32_t id = edge_count++;
    edges[id] = (sim_edge_t){
        .node_a = node_a, .node_b = node_b,
        .wire_id = wire_id, .active = true,
    };
    return (int32_t)id;
}

void sim_remove_edge_by_wire(uint16_t wire_id) {
    for (uint32_t i = 0; i < edge_count; i++) {
        if (edges[i].active && edges[i].wire_id == wire_id) {
            edges[i].active = false;
        }
    }
}

/* ---- Bus management ---- */

int32_t sim_add_bus(const uint16_t *members_ptr, uint8_t count) {
    if (count > SIM_MAX_BUS_MEMBERS) count = SIM_MAX_BUS_MEMBERS;
    /* Reuse inactive slot */
    for (uint32_t i = 0; i < bus_count; i++) {
        if (!buses[i].active) {
            buses[i].count = count;
            memcpy(buses[i].members, members_ptr, count * sizeof(uint16_t));
            buses[i].active = true;
            return (int32_t)i;
        }
    }
    if (bus_count >= SIM_MAX_BUSES) return -1;
    uint32_t id = bus_count++;
    buses[id].count = count;
    memcpy(buses[id].members, members_ptr, count * sizeof(uint16_t));
    buses[id].active = true;
    return (int32_t)id;
}

void sim_remove_bus(uint16_t bus_id) {
    if (bus_id < SIM_MAX_BUSES) {
        buses[bus_id].active = false;
    }
}

/* ---- Net assignment (flood fill) ---- */

static void assign_nets(void) {
    /* Clear all net assignments */
    for (uint32_t i = 0; i < node_count; i++) {
        if (nodes[i].active) nodes[i].net_id = -1;
    }

    memset(bfs_visited, 0, sizeof(bfs_visited));
    int16_t net_id = 0;

    for (uint32_t start = 0; start < node_count; start++) {
        if (!nodes[start].active || bfs_visited[start]) continue;

        /* BFS from this node */
        uint32_t head = 0, tail = 0;
        bfs_queue[tail++] = (uint16_t)start;
        bfs_visited[start] = true;

        while (head < tail) {
            uint16_t cur = bfs_queue[head++];
            nodes[cur].net_id = net_id;

            /* Follow edges */
            for (uint32_t e = 0; e < edge_count; e++) {
                if (!edges[e].active) continue;
                uint16_t neighbor = UINT16_MAX;
                if (edges[e].node_a == cur) neighbor = edges[e].node_b;
                else if (edges[e].node_b == cur) neighbor = edges[e].node_a;
                if (neighbor < node_count && !bfs_visited[neighbor] && nodes[neighbor].active) {
                    bfs_visited[neighbor] = true;
                    if (tail < SIM_MAX_NODES) bfs_queue[tail++] = neighbor;
                }
            }

            /* Follow buses */
            for (uint32_t b = 0; b < bus_count; b++) {
                if (!buses[b].active) continue;
                bool cur_in_bus = false;
                for (uint8_t m = 0; m < buses[b].count; m++) {
                    if (buses[b].members[m] == cur) { cur_in_bus = true; break; }
                }
                if (!cur_in_bus) continue;
                for (uint8_t m = 0; m < buses[b].count; m++) {
                    uint16_t member = buses[b].members[m];
                    if (member < node_count && !bfs_visited[member] && nodes[member].active) {
                        bfs_visited[member] = true;
                        if (tail < SIM_MAX_NODES) bfs_queue[tail++] = member;
                    }
                }
            }
        }
        net_id++;
    }
}

/* ---- Voltage propagation ---- */

static sim_level_t resolve_net(int16_t net_id) {
    /*
     * For each net:
     *  - If any OUTPUT node drives HIGH and no OUTPUT drives LOW → HIGH
     *  - If any OUTPUT node drives LOW and no OUTPUT drives HIGH → LOW
     *  - If OUTPUT nodes disagree → CONFLICT
     *  - If no OUTPUT, check pull resistors
     *  - Otherwise FLOAT
     */
    bool has_high = false, has_low = false;
    bool has_pull_up = false, has_pull_down = false;

    for (uint32_t i = 0; i < node_count; i++) {
        if (!nodes[i].active || nodes[i].net_id != net_id) continue;

        if (nodes[i].dir == SIM_DIR_OUTPUT) {
            if (nodes[i].driven == SIM_LEVEL_HIGH) has_high = true;
            if (nodes[i].driven == SIM_LEVEL_LOW)  has_low = true;
        }
        if (nodes[i].pull == SIM_PULL_UP)   has_pull_up = true;
        if (nodes[i].pull == SIM_PULL_DOWN) has_pull_down = true;
    }

    if (has_high && has_low) return SIM_LEVEL_CONFLICT;
    if (has_high) return SIM_LEVEL_HIGH;
    if (has_low)  return SIM_LEVEL_LOW;
    if (has_pull_up && !has_pull_down) return SIM_LEVEL_HIGH;
    if (has_pull_down && !has_pull_up) return SIM_LEVEL_LOW;
    return SIM_LEVEL_FLOAT;
}

/* ---- Tick ---- */

uint32_t sim_tick(void) {
    /* 1. Rebuild nets */
    assign_nets();

    /* 2. Resolve each net and record changes */
    change_count = 0;
    conflict_count = 0;

    /* Find max net_id */
    int16_t max_net = -1;
    for (uint32_t i = 0; i < node_count; i++) {
        if (nodes[i].active && nodes[i].net_id > max_net)
            max_net = nodes[i].net_id;
    }

    /* Resolve per-net */
    for (int16_t n = 0; n <= max_net; n++) {
        sim_level_t level = resolve_net(n);

        if (level == SIM_LEVEL_CONFLICT) {
            /* Record conflict: find the two drivers */
            uint16_t da = UINT16_MAX, db = UINT16_MAX;
            for (uint32_t i = 0; i < node_count; i++) {
                if (!nodes[i].active || nodes[i].net_id != n) continue;
                if (nodes[i].dir != SIM_DIR_OUTPUT) continue;
                if (da == UINT16_MAX) da = (uint16_t)i;
                else if (db == UINT16_MAX) { db = (uint16_t)i; break; }
            }
            if (conflict_count < SIM_MAX_NODES) {
                conflict_buf[conflict_count++] = (sim_conflict_t){
                    .net_id = n, .driver_a = da, .driver_b = db,
                };
            }
        }

        /* Apply resolved level to all nodes in this net */
        for (uint32_t i = 0; i < node_count; i++) {
            if (!nodes[i].active || nodes[i].net_id != n) continue;
            sim_level_t old = nodes[i].resolved;
            nodes[i].resolved = level;
            if (old != level && change_count < SIM_MAX_NODES) {
                change_buf[change_count++] = (sim_change_t){
                    .node_id = (uint16_t)i,
                    .old_level = old,
                    .new_level = level,
                };
            }
        }
    }

    return change_count;
}

/* ---- Pin state ---- */

void sim_set_pin(uint16_t node_id, sim_direction_t dir,
                 sim_level_t driven, sim_pull_t pull) {
    if (node_id >= SIM_MAX_NODES || !nodes[node_id].active) return;
    nodes[node_id].dir = dir;
    nodes[node_id].driven = driven;
    nodes[node_id].pull = pull;
}

sim_level_t sim_get_level(uint16_t node_id) {
    if (node_id >= SIM_MAX_NODES || !nodes[node_id].active) return SIM_LEVEL_FLOAT;
    return nodes[node_id].resolved;
}

int16_t sim_get_net(uint16_t node_id) {
    if (node_id >= SIM_MAX_NODES || !nodes[node_id].active) return -1;
    return nodes[node_id].net_id;
}

/* ---- Query helpers ---- */

uint32_t sim_get_net_nodes(uint16_t node_id, uint16_t *out_buf, uint32_t out_max) {
    if (node_id >= SIM_MAX_NODES || !nodes[node_id].active) return 0;
    int16_t nid = nodes[node_id].net_id;
    if (nid < 0) return 0;
    uint32_t count = 0;
    for (uint32_t i = 0; i < node_count && count < out_max; i++) {
        if (nodes[i].active && nodes[i].net_id == nid) {
            out_buf[count++] = (uint16_t)i;
        }
    }
    return count;
}

uint32_t sim_get_conflicts(sim_conflict_t *out_buf, uint32_t out_max) {
    uint32_t n = conflict_count < out_max ? conflict_count : out_max;
    memcpy(out_buf, conflict_buf, n * sizeof(sim_conflict_t));
    return n;
}

uint32_t sim_get_changes(sim_change_t *out_buf, uint32_t out_max) {
    uint32_t n = change_count < out_max ? change_count : out_max;
    memcpy(out_buf, change_buf, n * sizeof(sim_change_t));
    return n;
}

uint32_t sim_node_count(void) { return node_count; }
uint32_t sim_edge_count(void) { return edge_count; }

/* Shared buffer pointers for zero-copy JS/Python interop */
sim_node_t     *sim_get_node_ptr(uint16_t node_id) {
    if (node_id >= SIM_MAX_NODES) return &nodes[0];
    return &nodes[node_id];
}
sim_change_t   *sim_get_change_buf(void) { return change_buf; }
sim_conflict_t *sim_get_conflict_buf(void) { return conflict_buf; }
uint16_t       *sim_get_net_buf(void) { return net_buf; }
