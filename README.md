# Kung Fu Chess — Iteration 10 (Final Iteration) Deliverable

This is the **only-the-last-iteration** deliverable: the fully layered
architecture from the design guide (Sections 4–12), hardened, tested, and
extended with **one extra-route feature: simultaneous movement of
multiple pieces** (Section 3 / Iteration 10).

Every module has a long docstring at the top explaining, in detail, *why*
it exists, *why* it's shaped the way it is, and *why* specific tools
(dataclasses, Enums, dict-dispatch/Strategy) were chosen over the
alternatives. This README is the map; the docstrings are the territory.

## Running it

```bash
pip install pytest
python -m pytest tests/ -v      # 55 unit tests + 7 text-integration tests
python -m kungfu_chess.app       # prints a starting chess position
```

## Package structure

```
kungfu_chess/
  config.py              # shared constants + the MAX_CONCURRENT_MOTIONS knob
  model/
    position.py           # Position: immutable (row, col) value object
    piece.py               # Piece: identity + PieceState lifecycle enum
    board.py                # Board: logical occupancy only
    game_state.py            # GameState: game_over / winner
  rules/
    piece_rules.py           # legal_destinations() per piece, Strategy pattern
    rule_engine.py            # RuleEngine: read-only move legality
  realtime/
    motion.py                  # Motion / ArrivalEvent data holders
    real_time_arbiter.py        # RealTimeArbiter: timing + Iteration 10 feature
  engine/
    game_engine.py                # GameEngine: the Application Service
  input/
    board_mapper.py                # pixel -> cell
    controller.py                   # click interpretation + selection
  io/
    board_parser.py                  # text -> Board
    board_printer.py                  # Board -> text
  view/
    renderer.py                        # GameSnapshot -> drawable lines
  texttests/
    script_parser.py                    # .kfc text -> command list
    script_runner.py                     # drives Controller/GameEngine, never Board
  app.py                                  # composition root

tests/
  unit/            # one file per class, per Section 16's ownership table
  integration/
    scripts/*.kfc  # 01..07, the last one (07) demonstrates simultaneous movement
    test_text_scripts.py
```

## Layer ownership → pattern → why (quick reference)

| Layer | Pattern name | Why this tool, briefly |
|---|---|---|
| `Position` | Value Object (frozen dataclass) | Immutable, hashable, used as dict/set keys; equality "for free" |
| `Piece` | Entity (mutable dataclass) + Enum lifecycle | Has identity that outlives mutation; `PieceState` enum instead of raw strings to make illegal states impossible |
| `Board` | Aggregate root over occupancy | Two indexes (`by_cell`, `by_id`) because two different questions get asked of it, both on the hot path |
| `PieceRules` | Strategy (dict dispatch) | Adding a new piece = one function + one dict entry, never touches existing pieces' logic |
| `RuleEngine` | Validation Service | Pure, read-only, returns a stable `reason` code — never mutates, never knows about `game_over` |
| `RealTimeArbiter` | Owns a *collection* of Motions | The whole extra-route feature (simultaneous movement) is this file allowing >1 active Motion, gated by one config number |
| `GameEngine` | Application Service | The only class allowed to know about Board + RuleEngine + RealTimeArbiter + GameState together; sequences the guard checks |
| `Controller` | Adapter (input) | Converts pixel clicks into, at most, one `GameEngine.request_move` call; owns selection state and nothing else |
| `BoardMapper` | Adapter (coordinates) | Isolated on purpose — only class that knows pixels exist |
| `BoardParser` / `BoardPrinter` | Adapter (text I/O) | Shared by both the app and the test runner — not test-only helpers |
| `Renderer` | View Adapter | Receives read-only `GameSnapshot`, never live `Board`/`Piece` |
| `ScriptRunner` | Command-script test harness | Always drives the real public path (Controller → GameEngine), the "forbidden shortcut" (calling `Board.move_piece` directly) is never used |

##  / extra-route feature: simultaneous movement

Full **architecture impact note** (affected layers, new state, public API
impact, required tests, unchanged layers) lives at the top of
`realtime/real_time_arbiter.py`, exactly where Section 17/10 of the guide
says to write it — *before* the implementation it documents.

One-paragraph summary: the common route allowed only one active `Motion`
system-wide (`GameEngine` rejected any second click with
`"motion_in_progress"`). The extra route replaces that *global* guard
with a *per-piece* guard (`RealTimeArbiter.can_start_motion(piece_id)`),
governed by one config number, `config.MAX_CONCURRENT_MOTIONS`:

- `1` → exactly reproduces the old common-route behaviour (regression-safe)
- `None` → fully unlimited concurrent motions (the extra-route default)
- any `N` → capped concurrency, useful for tuning/testing

This is the "keep it flexible" requirement: switching behaviour is a
one-line constructor argument, not a subclass or a second code path.

`tests/integration/scripts/07_simultaneous_movement.kfc` is the
user-visible proof: two different rooks, on opposite sides of the board,
both start moving from the same `wait`-free burst of clicks, and both are
shown mid-flight (unchanged board) and then arrived (both moved) — using
only `print board`, per the DSL's "one assertion style" rule (Section 14).
