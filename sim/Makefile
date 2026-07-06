# Build sim.wasm - electrical continuity simulation engine
# Requires wasi-sdk (same as ctpy-local/ports/wasix/host)

WASI_SDK ?= $(HOME)/.local/bin/wasi-sdk-32.0-x86_64-linux
CC = $(WASI_SDK)/bin/clang --target=wasm32-wasip1 --sysroot=$(WASI_SDK)/share/wasi-sysroot

BUILD = ../wasm
CFLAGS = -O2 -Wall -flto
LDFLAGS = -mexec-model=reactor -Wl,--no-entry \
	-Wl,--export=sim_init \
	-Wl,--export=sim_add_node \
	-Wl,--export=sim_remove_node \
	-Wl,--export=sim_add_edge \
	-Wl,--export=sim_remove_edge_by_wire \
	-Wl,--export=sim_add_bus \
	-Wl,--export=sim_remove_bus \
	-Wl,--export=sim_set_pin \
	-Wl,--export=sim_tick \
	-Wl,--export=sim_get_level \
	-Wl,--export=sim_get_net \
	-Wl,--export=sim_get_net_nodes \
	-Wl,--export=sim_get_conflicts \
	-Wl,--export=sim_get_changes \
	-Wl,--export=sim_node_count \
	-Wl,--export=sim_edge_count \
	-Wl,--export=sim_get_node_ptr \
	-Wl,--export=sim_get_change_buf \
	-Wl,--export=sim_get_conflict_buf \
	-Wl,--export=sim_get_net_buf \
	-Wl,--gc-sections

TARGET = $(BUILD)/sim.wasm

all: $(TARGET)

$(TARGET): sim.c sim.h
	@mkdir -p $(BUILD)
	$(CC) $(CFLAGS) $(LDFLAGS) -o $@ sim.c

clean:
	rm -f $(TARGET)

.PHONY: all clean
