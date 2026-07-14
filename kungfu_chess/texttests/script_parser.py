"""
script_parser: raw .kfc text -> a list of (command, ...) tuples. This
file is purely about DSL *syntax* (Section 13, extended for the Jump
extra-route: Board, click, jump, wait, print board) - it has no idea what
a "legal move" or a "piece" is, and never touches GameEngine.

WHY PARSING IS A FREE FUNCTION HERE, SEPARATE FROM ScriptRunner:
Splitting "understand the text" from "execute the commands" mirrors the
same split as BoardParser/BoardPrinter vs the rest of the app: a parser
with no side effects is trivial to unit-test (feed it a string, assert on
the returned command list) without any Board/GameEngine/Controller
fixture at all. ScriptRunner can then be tested (or reasoned about)
assuming parsing already works, instead of every runner test also being
an implicit parser test.

WHY BOARD/PRINT BLOCKS ARE DELIMITED BY "next keyword or blank line"
RATHER THAN AN EXPLICIT END MARKER:
The DSL examples in the guide never use an explicit terminator for a
board or expected-output block - the block simply ends where the next
`click` / `wait` / `print board` / `Board` line (or the file) begins.
Matching that exact convention (rather than inventing a new "END" token
the guide doesn't specify) keeps every example already in the guide
parseable unmodified.
"""

from typing import List, Tuple


def _is_keyword_line(line: str) -> bool:
    s = line.strip()
    return (s == "Board" or s == "print board"
            or s.startswith("click ") or s.startswith("jump ") or s.startswith("wait "))


def parse_script(text: str) -> List[Tuple]:
    lines = text.splitlines()
    commands = []
    i, n = 0, len(lines)

    while i < n:
        line = lines[i].strip()

        if not line:
            i += 1
            continue

        if line == "Board":
            i += 1
            rows = []
            while i < n and lines[i].strip() and not _is_keyword_line(lines[i]):
                rows.append(lines[i].strip().split())
                i += 1
            commands.append(("board", rows))

        elif line.startswith("click "):
            _, x, y = line.split()
            commands.append(("click", int(x), int(y)))
            i += 1

        elif line.startswith("jump "):
            _, x, y = line.split()
            commands.append(("jump", int(x), int(y)))
            i += 1

        elif line.startswith("wait "):
            _, ms = line.split()
            commands.append(("wait", int(ms)))
            i += 1

        elif line == "print board":
            i += 1
            rows = []
            while i < n and lines[i].strip() and not _is_keyword_line(lines[i]):
                rows.append(lines[i].strip().split())
                i += 1
            commands.append(("print", rows))

        else:
            i += 1  # unrecognized line: ignored, keeps the parser lenient

    return commands
