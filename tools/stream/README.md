# STREAM (pinned)

`stream.c` is John D. McCalpin's STREAM 5.10, copied unmodified from
<https://github.com/jeffhammond/STREAM> at commit `6703f7504a38a8da96b353cadafa64d3c2d7a2d3`
(SHA-256 `c388924eb140fda95f534cdb808ae7f1f8ebb18da41d8aec1b512a3c8d303c9b`; see `MANIFEST.json`).
`python -m smallpc.microbench` verifies the hash before every build and refuses to build on a mismatch.

Licence: the terms in the file header (free to use, redistribute, and modify for own use; results
from modified source or from runs outside the STREAM Run Rules must be labelled as variants). We
compile with `-DSTREAM_ARRAY_SIZE=... -DNTIMES=...` and do not edit the source; we do not claim
official STREAM results.

Build (done by the driver): `gcc -O3 -march=native -fopenmp -DSTREAM_ARRAY_SIZE=100000000 -DNTIMES=20
-mcmodel=medium stream.c -o build/tools/stream`.
