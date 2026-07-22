# KungFuChess WebSocket Protocol

Every message is a single JSON object per WebSocket text frame, tagged
with a `"type"` field. Implemented in `kungfu_chess/network/protocol.py`
(`encode`/`decode`).

**Message order is not a reply contract.** The server broadcasts
`game_state_update` on a fixed ~20Hz tick *and* immediately after any
accepted move, independently of replying to a specific client's request
(`error`, when a request is rejected). These two sources race each
other, so the very next message a client receives after sending a
request is **not guaranteed** to be that request's reply - it may be an
unrelated broadcast that happened to be scheduled first. A client must
dispatch every incoming message by its `type` (and content), never by
its position relative to something the client just sent.

**`move_request`/`jump_request` carry a `request_id`.** An accepted
request gets no direct reply at all (only the broadcast above); a
rejected one gets an `error` with that same `request_id` echoed back, so
a client with more than one request in flight at once (e.g. sent before
the first resolved) can tell which one a given `error` is about.
`request_id` is any string the client chooses - the server never
interprets it, only copies it. `game_state_update` never carries one:
it's a broadcast, not a reply to a specific request.

A `Position` is always `{"row": int, "col": int}`.

## Client -> Server

### `move_request`

```json
{"type": "move_request", "request_id": "3", "source": {"row": 6, "col": 4}, "destination": {"row": 4, "col": 4}}
```

### `jump_request`

```json
{"type": "jump_request", "request_id": "4", "source": {"row": 6, "col": 4}}
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
{"type": "error", "reason": "wrong_color", "request_id": "3"}
```

`request_id` is the same value the triggering `move_request`/
`jump_request` carried - `null` when the request couldn't be identified
at all (a `malformed_message`/`unknown_message_type` failure means the
payload may not have decoded far enough to recover it).

Known `reason` values as of this branch: `malformed_message`,
`unknown_message_type`, `spectators_cannot_move`, `wrong_color`, plus
whatever reason string `GameEngine.request_move`/`request_jump` returns
for a rejected move (`game_over`, `motion_in_progress`,
`outside_board`, `illegal_piece_move`, `empty_cell`, ...) - `Error`
never invents its own vocabulary for chess-legality reasons, it just
forwards GameEngine's.