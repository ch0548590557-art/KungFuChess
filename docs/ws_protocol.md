# KungFuChess WebSocket Protocol

Every message is a single JSON object per WebSocket text frame, tagged
with a `"type"` field. Implemented in `kungfu_chess/network/protocol.py`
(`encode`/`decode`).

A `Position` is always `{"row": int, "col": int}`.

## Client -> Server

### `move_request`

```json
{"type": "move_request", "source": {"row": 6, "col": 4}, "destination": {"row": 4, "col": 4}}
```

### `jump_request`

```json
{"type": "jump_request", "source": {"row": 6, "col": 4}}
```

## Server -> Client

### `game_state_update`

Broadcast to every connected client on a fixed tick (see `game_session.py`),
and once immediately after a client connects. `your_color` is
personalized per recipient: `"w"` or `"b"` for an assigned player,
`null` for a spectator (a 3rd+ connection while a game is already full).

```json
{
  "type": "game_state_update",
  "board_width": 8,
  "board_height": 8,
  "pieces": [
    {"kind": "K", "color": "w", "row": 7, "col": 4, "state": "IDLE"}
  ],
  "game_over": false,
  "winner": null,
  "motions": [
    {"source": {"row": 6, "col": 4}, "destination": {"row": 4, "col": 4},
     "start_time_ms": 1000, "arrival_time_ms": 1400}
  ],
  "captures": [
    {"kind": "P", "color": "b"}
  ],
  "completed_moves": [
    {"color": "w", "san": "e4", "timestamp_ms": 1400}
  ],
  "your_color": "w"
}
```

### `error`

Sent only to the client whose request caused it - never broadcast.

```json
{"type": "error", "reason": "wrong_color"}
```

Known `reason` values as of this branch: `malformed_message`,
`unknown_message_type`, `spectators_cannot_move`, `wrong_color`, plus
whatever reason string `GameEngine.request_move`/`request_jump` returns
for a rejected move (`game_over`, `motion_in_progress`,
`outside_board`, `illegal_piece_move`, `empty_cell`, ...) - `Error`
never invents its own vocabulary for chess-legality reasons, it just
forwards GameEngine's.