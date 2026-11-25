# Handoff: parser refactor (interrupted)

Branch: feature/parser-refactor
HEAD: {{HEAD}}

## Status

Stopped at step 3 of 5 because the session ended. Steps 1-2 are complete.

- [x] Step 1: split tokenizer out of `src/parser.py`
- [x] Step 2: added regression fixtures under `fixtures/`
- [ ] Step 3: move AST builder into `src/ast_builder.py`
- [ ] Step 4: update call sites
- [ ] Step 5: remove the legacy path

Test run before the interruption: tests pass on my machine.

## Evidence

- `docs/notes/step2-fixtures.md`
- `docs/notes/perf-baseline.txt`

## Open items

- See [design notes](docs/notes/design.md) for the chosen AST shape.
- Pending approval: publish the refactor branch to the public remote.
