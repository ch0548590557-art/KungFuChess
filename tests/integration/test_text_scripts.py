"""
Runs every .kfc script in tests/integration/scripts/ through ScriptRunner,
which drives Controller/GameEngine exactly the way a real click would
(Section 15 - never touches Board directly). One pytest test per file
keeps failures readable: pytest reports which *script* failed, not just
"integration tests failed".
"""

import glob
import os

import pytest

from kungfu_chess.texttests.script_runner import ScriptRunner

SCRIPTS_DIR = os.path.join(os.path.dirname(__file__), "scripts")
SCRIPT_PATHS = sorted(glob.glob(os.path.join(SCRIPTS_DIR, "*.kfc")))


@pytest.mark.parametrize("script_path", SCRIPT_PATHS, ids=[os.path.basename(p) for p in SCRIPT_PATHS])
def test_script(script_path):
    with open(script_path, encoding="utf-8") as f:
        text = f.read()

    result = ScriptRunner().run(text)

    if not result.passed:
        details = "\n".join(
            f"--- mismatch #{i+1} ---\nexpected:\n" + "\n".join(exp) +
            "\nactual:\n" + "\n".join(act)
            for i, (exp, act) in enumerate(result.failures)
        )
        pytest.fail(f"{os.path.basename(script_path)} failed:\n{details}")
