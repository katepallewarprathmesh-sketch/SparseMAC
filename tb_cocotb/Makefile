# cocotb Makefile for SparseMAC (Verilator backend)
SIM = verilator
TOPLEVEL_LANG = verilog
VERILOG_SOURCES = $(PWD)/../rtl/sparsemac.sv $(PWD)/../rtl/sparse_scheduler.sv
TOPLEVEL = sparsemac
MODULE = test_sparsemac
COMPILE_ARGS += -Wno-WIDTHEXPAND
include $(shell cocotb-config --makefiles)/Makefile.sim
