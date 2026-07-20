import kungfu_chess.graphics.move_log as move_log_module
from kungfu_chess.graphics.move_log import MoveLog, format_move_time


def test_format_move_time_examples_from_the_spec():
    assert format_move_time(2314) == "00:02.314"
    assert format_move_time(13401) == "00:13.401"
    assert format_move_time(65908) == "01:05.908"


def test_format_move_time_at_zero():
    assert format_move_time(0) == "00:00.000"


def test_update_with_none_is_treated_as_no_moves_yet():
    log = MoveLog()

    log.update(None)

    assert log.rows_for('w') == []
    assert log.rows_for('b') == []


def test_update_splits_interleaved_moves_by_color_preserving_order():
    log = MoveLog()

    log.update([('w', 'e4', 2000), ('b', 'e5', 5000), ('w', 'Nf3', 8000)])

    assert log.rows_for('w') == [("00:02.000", "e4"), ("00:08.000", "Nf3")]
    assert log.rows_for('b') == [("00:05.000", "e5")]


def test_update_called_again_with_a_longer_list_only_appends_the_new_tail():
    log = MoveLog()
    log.update([('w', 'e4', 2000)])
    log.update([('w', 'e4', 2000), ('b', 'e5', 5000)])

    assert log.rows_for('w') == [("00:02.000", "e4")]
    assert log.rows_for('b') == [("00:05.000", "e5")]


def test_rows_already_produced_are_never_reordered_or_overwritten():
    log = MoveLog()
    log.update([('w', 'e4', 2000)])
    first_call_rows = log.rows_for('w')

    log.update([('w', 'e4', 2000), ('w', 'Nf3', 8000), ('w', 'Bb5', 9000)])
    second_call_rows = log.rows_for('w')

    # The row produced by the first call must still be there, unchanged,
    # at the same leading position - not replaced, not reordered.
    assert second_call_rows[0] == first_call_rows[0]
    assert second_call_rows == [("00:02.000", "e4"), ("00:08.000", "Nf3"), ("00:09.000", "Bb5")]


def test_rows_for_returns_a_copy_the_caller_cannot_use_to_mutate_the_model():
    log = MoveLog()
    log.update([('w', 'e4', 2000)])

    rows = log.rows_for('w')
    rows.append(("99:99.999", "hacked"))

    assert log.rows_for('w') == [("00:02.000", "e4")]


def test_rows_for_an_unseen_color_is_an_empty_list_rather_than_raising():
    log = MoveLog()

    assert log.rows_for('w') == []


def test_a_shorter_than_before_list_is_treated_defensively_as_nothing_new():
    # completed_moves is documented as append-only/growing; if a
    # shorter list is ever handed in anyway, MoveLog must not rewind
    # its cursor and reprocess entries it already turned into rows
    # (which would duplicate them).
    log = MoveLog()
    log.update([('w', 'e4', 2000), ('b', 'e5', 5000)])

    log.update([('w', 'e4', 2000)])  # shorter than what's already consumed

    assert log.rows_for('w') == [("00:02.000", "e4")]
    assert log.rows_for('b') == [("00:05.000", "e5")]


def test_update_does_not_reformat_already_consumed_entries_on_later_calls(monkeypatch):
    # Cheap, direct observation of the "no full rescan" requirement:
    # format_move_time is only called once per genuinely NEW entry,
    # never again for entries a previous update() call already turned
    # into a row.
    call_count = {"n": 0}
    real_format = move_log_module.format_move_time

    def counting_format(timestamp_ms):
        call_count["n"] += 1
        return real_format(timestamp_ms)

    monkeypatch.setattr(move_log_module, "format_move_time", counting_format)

    log = MoveLog()
    log.update([('w', 'e4', 2000), ('b', 'e5', 5000)])
    assert call_count["n"] == 2

    # Same two entries plus one brand-new one: only the new one should
    # trigger a fresh format_move_time call, not all three.
    log.update([('w', 'e4', 2000), ('b', 'e5', 5000), ('w', 'Nf3', 8000)])
    assert call_count["n"] == 3


def test_hundreds_of_incremental_single_move_updates_keep_full_history_in_order():
    log = MoveLog()
    moves = []
    for i in range(300):
        color = 'w' if i % 2 == 0 else 'b'
        moves.append((color, f"m{i}", i * 1000))
        log.update(moves)  # simulates one new move arriving per frame

    white_rows = log.rows_for('w')
    black_rows = log.rows_for('b')
    assert len(white_rows) == 150
    assert len(black_rows) == 150
    assert white_rows[0] == ("00:00.000", "m0")
    assert white_rows[-1][1] == "m298"
    assert black_rows[-1][1] == "m299"
