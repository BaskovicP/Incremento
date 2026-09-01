from __future__ import annotations

import pytest

from scripts import mutation_smoke


def test_apply_mutation_rejects_a_syntactically_invalid_mutant() -> None:
    mutation = mutation_smoke.Mutation(
        name="invalid_python",
        original="return 1",
        replacement="return (",
    )

    with pytest.raises(SyntaxError):
        mutation_smoke.apply_mutation("def value():\n    return 1\n", mutation)
