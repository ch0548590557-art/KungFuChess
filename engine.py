"""The game engine: owns all mutable state (board, clock, selection,
pending moves, airborne jumps, game-over flag) and is the only place that
knows how the four command types (click / jump / wait / print) interact.

main.py never touches board/clock/etc directly - it only calls
engine.handle_command(cmd) in a loop. That's the encapsulation boundary.
"""

import math

import config
from board import Board
from moves import PendingMove, AirborneJump
from piece_rules import is_legal_move


def pixel_to_cell(x, y):
    """Raw click/jump pixel coordinates -> (row, col) board indices."""
    col = math.ceil(x / config.PIXELS_PER_SQUARE) - 1
    row = math.ceil(y / config.PIXELS_PER_SQUARE) - 1
    return row, col


class GameEngine:

    def __init__(self, board_rows):
        self._board = Board(board_rows)
        self._clock = 0
        self._selected = None          # (row, col) or None
        self._pending_moves = []       # list[PendingMove]
        self._airborne_jumps = []      # list[AirborneJump]
        self._game_over = False

    def handle_command(self, cmd):
        if cmd.startswith("jump"):
            self._handle_jump(cmd)
        elif cmd.startswith("click"):
            self._handle_click(cmd)
        elif cmd.startswith("wait"):
            self._handle_wait(cmd)
        elif cmd == "print board":
            self._print_board()

    # ---- jump --------------------------------------------------------

    def _handle_jump(self, cmd):
        if self._game_over:
            return

        _, x, y = cmd.split()
        row, col = pixel_to_cell(int(x), int(y))

        if self._board.in_bounds(row, col):
            is_moving = any(m.starts_at(row, col) for m in self._pending_moves)
            if not self._board.is_empty(row, col) and not is_moving:
                self._airborne_jumps.append(AirborneJump(
                    row=row, col=col,
                    start_time=self._clock,
                    end_time=self._clock + config.JUMP_DURATION_MS,
                    piece=self._board.get(row, col),
                ))

        self._selected = None

    # ---- click -------------------------------------------------------

    def _handle_click(self, cmd):
        if self._game_over:
            return

        _, x, y = cmd.split()
        row, col = pixel_to_cell(int(x), int(y))

        if not self._board.in_bounds(row, col):
            return

        if any(m.starts_at(row, col) for m in self._pending_moves):
            self._selected = None
            return

        tok = self._board.get(row, col)

        if tok != '.':
            if self._selected and self._board.color_at(*self._selected) != tok[0]:
                self._try_queue_move(row, col)
            else:
                self._selected = (row, col)
        else:
            if self._selected:
                self._try_queue_move(row, col)
            self._selected = None

    def _try_queue_move(self, to_r, to_c):
        sel_r, sel_c = self._selected
        piece_type = self._board.type_at(sel_r, sel_c)

        if is_legal_move(self._board, piece_type, sel_r, sel_c, to_r, to_c):
            self._pending_moves.append(PendingMove(
                arrival_time=self._clock + config.MOVE_DURATION_MS,
                from_r=sel_r, from_c=sel_c,
                to_r=to_r, to_c=to_c,
                piece=self._board.get(sel_r, sel_c),
            ))
        self._selected = None

    # ---- wait --------------------------------------------------------

    def _handle_wait(self, cmd):
        wait_time = int(cmd.split()[1])
        target_time = self._clock + wait_time

        self._pending_moves.sort(key=lambda m: m.arrival_time)
        remaining_moves = []

        for move in self._pending_moves:
            if self._game_over:
                break

            if move.arrival_time <= target_time:
                if self._apply_move(move, remaining_moves):
                    break
            else:
                remaining_moves.append(move)

        self._airborne_jumps = [j for j in self._airborne_jumps if j.is_active_after(target_time)]
        self._pending_moves = remaining_moves
        self._clock = target_time

    def _apply_move(self, move, remaining_moves):
        """Executes one arrived move (capture/airborne/promotion/game-over
        checks). Returns True if this move ended the game."""
        r1, c1, r2, c2 = move.from_r, move.from_c, move.to_r, move.to_c
        piece = move.piece

        if self._is_captured_midair(move):
            self._board.clear(r1, c1)
            return False

        if not self._board.is_empty(r2, c2) and self._board.type_at(r2, c2) == config.KING_TYPE:
            self._game_over = True

        piece = self._maybe_promote(piece, r2)

        self._board.set(r2, c2, piece)
        if self._board.get(r1, c1) == move.piece:
            self._board.clear(r1, c1)

        remaining_moves[:] = [m for m in remaining_moves if not m.starts_at(r2, c2)]

        if self._game_over:
            remaining_moves.clear()
            return True

        return False

    def _is_captured_midair(self, move):
        for jump in self._airborne_jumps:
            if jump.covers(move.to_r, move.to_c, move.arrival_time) and jump.is_enemy_of(move.piece):
                return True
        return False

    def _maybe_promote(self, piece, landing_row):
        if piece[1] != config.PAWN_TYPE:
            return piece
        color = piece[0]
        promotes = (
            (color == 'w' and landing_row == 0)
            or (color == 'b' and landing_row == self._board.height - 1)
        )
        return color + config.PROMOTION_PIECE_TYPE if promotes else piece

    # ---- print ---------------------------------------------------------

    def _print_board(self):
        for row in self._board.row_strings():
            print(row)
