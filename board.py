class Board(object):
    """Wraps the raw board grid so nothing outside this class needs to know
    how a square's contents are represented.

    Today a square holds a 2-character string ('wP', 'bK', ...) or '.' for
    empty. If that representation ever changes (e.g. to a packed binary/int
    encoding to save memory), only the methods below need to change - every
    caller in the rest of the codebase goes through this class instead of
    touching the underlying grid directly.
    """

    def __init__(self, rows):
        # rows: list[list[str]] - kept private ("_rows") on purpose, so no
        # other class can reach in and read/mutate it directly.
        self._rows = rows

    @property
    def width(self):
        return len(self._rows[0])

    @property
    def height(self):
        return len(self._rows)

    def in_bounds(self, r, c):
        return 0 <= r < self.height and 0 <= c < self.width

    def is_empty(self, r, c):
        return self._rows[r][c] == '.'

    def get(self, r, c):
        """Returns the raw token at (r, c). Used only where the caller
        genuinely needs the whole piece (e.g. to store it on a move)."""
        return self._rows[r][c]

    def set(self, r, c, token):
        self._rows[r][c] = token

    def clear(self, r, c):
        self._rows[r][c] = '.'

    def color_at(self, r, c):
        return self._rows[r][c][0]

    def type_at(self, r, c):
        return self._rows[r][c][1]

    def row_strings(self):
        """Board -> printable rows, for the 'print board' command."""
        return [" ".join(row) for row in self._rows]
