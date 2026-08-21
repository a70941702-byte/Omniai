# Sandbox

`Sandbox.run_python` creates a fresh work directory, flattens supplied filenames, injects a network-denial bootstrap, applies POSIX CPU/data/process limits, caps output and enforces wall-clock timeout. The parent polls the owner kill switch and kills the process group when activated.

`run_pytest` executes tests inside the same isolation boundary.

The exact hard memory ceiling depends on host POSIX resource support; Python virtual-memory (`RLIMIT_AS`) is intentionally not used because it can prevent the interpreter from starting. A data-segment limit plus process/output/time limits is used instead.
