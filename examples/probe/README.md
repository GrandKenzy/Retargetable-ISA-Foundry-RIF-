# External MIR probes

This directory contains external MIR programs used to exercise targets. They
are deliberately kept separate from `.rif` target definitions and compiled
packages.

`probe_amd64/` contains the raw AMD64 programs and relocation/section fixtures
used by `AMD64_Baremetal` and by the Friendly Syntax equivalence checks.

`probe_friendlysyntax/` contains the external Friendly Syntax programs used by
the base target. `probe_friendlysyntax_qemu/` contains the QEMU target,
boot-specific MIR and its target-local assets.
