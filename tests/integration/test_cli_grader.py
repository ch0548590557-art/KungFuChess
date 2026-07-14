"""
End-to-end contract test for the course's automated-grader-style text
protocol.

WHY THIS FILE SHELLS OUT INSTEAD OF CALLING run_cli() DIRECTLY:
tests/unit/test_app.py already checks run_cli()'s behaviour in-process,
which is fast but doesn't prove the protocol survives an actual process
boundary (argv, real stdin/stdout, exit code). This file is that proof:
it invokes the project exactly the way an external grader would - piping
a whole text script into `python -m kungfu_chess.app` and diffing stdout
- through the *real*, single entry point, with no test-only shortcut.

This project has no main.py: kungfu_chess/app.py is the only runnable
entry point (see its module docstring for why). Its `main()` reads
piped stdin automatically whenever stdin isn't a terminal, which is
exactly the situation `subprocess.run(..., input=...)` creates below, so
no extra flag or argument is needed to select the CLI protocol.

Every case below is a literal transcription of the grader's own example
sessions (board parsing, selection/click rules, and one legality check
per piece type plus their "blocked by own piece" / "knight jumps"
variants), so a regression here means an external grader piping the same
scripts into this project would start failing too, not just an internal
assumption about it.
"""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def run_program(input_text: str) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "kungfu_chess.app"],
        input=input_text,
        text=True,
        capture_output=True,
        cwd=ROOT,
    )
    assert result.returncode == 0, (
        f"kungfu_chess.app exited with {result.returncode}, stderr:\n{result.stderr}"
    )
    return result.stdout.strip()


CASES = {
    "parse_rectangular_board_3x4": (
        """\
Board:
wK . . bK
. . . .
wR . . bR
Commands:
print board
""",
        """\
wK . . bK
. . . .
wR . . bR""",
    ),
    "parse_piece_tokens_and_colors": (
        """\
Board:
wK . bQ
. wN .
bP . wR
Commands:
print board
""",
        """\
wK . bQ
. wN .
bP . wR""",
    ),
    "reject_unknown_token": (
        """\
Board:
wK xZ
. .
Commands:
""",
        "ERROR UNKNOWN_TOKEN",
    ),
    "reject_row_width_mismatch": (
        """\
Board:
wK . .
. bK
Commands:
""",
        "ERROR ROW_WIDTH_MISMATCH",
    ),
    "select_piece_by_center_click": (
        """\
Board:
wK . .
. . .
. . .
Commands:
click 50 50
click 150 150
wait 1000
print board
""",
        """\
. . .
. wK .
. . .""",
    ),
    "click_empty_cell_does_not_select": (
        """\
Board:
wK . .
. . .
. . .
Commands:
click 150 150
click 250 250
wait 1000
print board
""",
        """\
wK . .
. . .
. . .""",
    ),
    "click_outside_board_is_ignored": (
        """\
Board:
wK . .
. . .
. . .
Commands:
click 350 50
click -10 50
print board
""",
        """\
wK . .
. . .
. . .""",
    ),
    "clicking_another_piece_replaces_selection": (
        """\
Board:
wR . wK
. . .
Commands:
click 50 50
click 250 50
click 250 150
wait 1000
print board
""",
        """\
wR . .
. . wK""",
    ),
    "king_one_step_valid": (
        """\
Board:
wK . .
. . .
. . .
Commands:
click 50 50
click 150 150
wait 1000
print board
""",
        """\
. . .
. wK .
. . .""",
    ),
    "king_two_steps_invalid": (
        """\
Board:
wK . .
. . .
. . .
Commands:
click 50 50
click 250 250
wait 1000
print board
""",
        """\
wK . .
. . .
. . .""",
    ),
    "rook_straight_valid": (
        """\
Board:
wR . .
Commands:
click 50 50
click 250 50
wait 2000
print board
""",
        ". . wR",
    ),
    "rook_diagonal_invalid": (
        """\
Board:
wR . .
. . .
. . .
Commands:
click 50 50
click 150 150
wait 1000
print board
""",
        """\
wR . .
. . .
. . .""",
    ),
    "bishop_diagonal_valid": (
        """\
Board:
wB . .
. . .
. . .
Commands:
click 50 50
click 250 250
wait 2000
print board
""",
        """\
. . .
. . .
. . wB""",
    ),
    "knight_L_valid": (
        """\
Board:
wN . .
. . .
. . .
Commands:
click 50 50
click 150 250
wait 3000
print board
""",
        """\
. . .
. . .
. wN .""",
    ),
    "queen_diagonal_valid": (
        """\
Board:
wQ . .
. . .
. . .
Commands:
click 50 50
click 250 250
wait 2000
print board
""",
        """\
. . .
. . .
. . wQ""",
    ),
    "rook_blocked_by_own_piece": (
        """\
Board:
wR wP .
Commands:
click 50 50
click 250 50
wait 2000
print board
""",
        "wR wP .",
    ),
    "bishop_blocked_by_own_piece": (
        """\
Board:
wB . .
. wP .
. . .
Commands:
click 50 50
click 250 250
wait 2000
print board
""",
        """\
wB . .
. wP .
. . .""",
    ),
    "knight_jumps_over_blockers": (
        """\
Board:
wN wP .
wP . .
. . .
Commands:
click 50 50
click 150 250
wait 3000
print board
""",
        """\
. wP .
wP . .
. wN .""",
    ),
}


@pytest.mark.parametrize("name", CASES.keys())
def test_grader_case(name):
    input_text, expected = CASES[name]
    assert run_program(input_text) == expected
