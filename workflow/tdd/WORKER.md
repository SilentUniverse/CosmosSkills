# Delegated engineering work

Load when a native delegated task needs the method for a bounded slice. Use its exact contract,
accepted input pointers, write scope and proof requirements. The host owns task state and recovery.

1. Read inputs and existing tests. Validate readiness evidence; do not silently change the contract.
2. Follow [SKILL.md](SKILL.md)'s method unless the user specified otherwise. Run scoped checks;
   shared delivery checks stay with the caller unless assigned.
3. Coordinate scope expansion before writing another task's files. Native parallelism is not isolation.
4. Return exact command/result, proof paths, changed paths and remaining gaps. Preserve failed attempts.
5. Write completion only when assigned and its proof gate passes; otherwise return evidence for
   integration. See [COMPLETION-RECORD.md](COMPLETION-RECORD.md).

A possible contract conflict returns the observation and exact clause to the caller. No nested
Cosmos workflow, fixed outcome protocol or execution ledger is required.
