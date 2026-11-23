# SparseMAC Makefile
.PHONY: test regress results formal lint clean

test: lint
	$(MAKE) -C tb_cocotb

regress: formal results

lint:
	verilator --lint-only -Wall --top-module sparsemac \
		rtl/sparsemac.sv rtl/sparse_scheduler.sv

formal:
	cd formal && sby -f scheduler.sby

results: test
	python3 scripts/run_ppa.py

clean:
	$(MAKE) -C tb_cocotb clean
	rm -rf formal/scheduler
