# test/
#
# One directory per testcase. Each contains:
#   *.pio              PIO software (assembled with pioasm)
#   test_*.py          pytest and/or cocotb modules
#   Makefile           assemble / test / sim targets
#
# Shared helpers:
#   mk/                Make fragments (pioasm, python, cocotb)
#   filelist.f         RTL compile order for simulation
#
# Example:
#   make -C test TEST=hello_world
#   make -C test/hello_world sim
