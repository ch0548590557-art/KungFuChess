"""
Renderer: draws a GameSnapshot. This course's "supplied drawing/image
library" is an external, environment-specific dependency (e.g. pygame),
which is out of scope for this automated deliverable - so this class
wraps drawing calls behind the same small interface the guide specifies
(Section 12), with a text-based stand-in `draw()` so the class is still
honestly testable without a graphics context. Swapping the stand-in body
for real pygame/PIL calls later touches only this file.

WHY Renderer RECEIVES GameSnapshot AND NEVER Board OR Piece DIRECTLY:
GameSnapshot is a read-only DTO built fresh by GameEngine.snapshot() on
each frame (Section 12: "live domain objects increase coupling and
create opportunities for accidental mutation from the view layer"). If
Renderer held a live Board reference, nothing in the type system would
stop a future rendering bug (e.g. a debug tool built "quickly" inside the
renderer) from calling board.move_piece() directly, silently bypassing
RuleEngine/RealTimeArbiter. A DTO makes that class of bug structurally
impossible: GameSnapshot simply has no mutating methods to call.

WHY draw() RETURNS A LIST OF LINES INSTEAD OF PRINTING DIRECTLY:
Returning data (not printing) keeps this class testable the same way as
every other layer - "Renderer smoke test draws a simple board without
mutating game state" (Section 17, Iteration 9) can assert on the
returned lines instead of capturing stdout, which is slower and more
brittle to test.
"""

from typing import List

from kungfu_chess.engine.game_engine import GameSnapshot


class Renderer:
    def draw(self, snapshot: GameSnapshot) -> List[str]:
        grid = [['.' for _ in range(snapshot.board_width)]
                for _ in range(snapshot.board_height)]

        for kind, color, row, col, state in snapshot.pieces:
            if state == "CAPTURED":
                continue
            grid[row][col] = f"{color}{kind}"

        lines = [" ".join(row) for row in grid]
        if snapshot.game_over:
            lines.append(f"GAME OVER - winner: {snapshot.winner}")
        return lines
