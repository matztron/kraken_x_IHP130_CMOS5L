The Yosys frontend does not understand all the System Verilog sytax parts.
Thats why we have this script to convert it to flattened verilog code:

Run like so:
./scripts/gen_tt_verilog.sh

That rewrites src/tt_bundle.v from the sources in test/filelist.f. You should see something like wrote .../src/tt_bundle.v (2752 lines).

CI does the same step automatically before GDS; you only need to run it locally when you want the committed bundle in sync after RTL changes.