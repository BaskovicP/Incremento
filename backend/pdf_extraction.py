"""Cooperative PDF extraction budgets and bounded external-process output."""

from concurrent.futures import CancelledError
from dataclasses import dataclass, field
import os
import subprocess
import tempfile
import time
from typing import Callable


class ExtractionLimit(RuntimeError):
    """Extraction exceeded its page, time or UTF-8 output budget."""


@dataclass
class ExtractionBudget:
    cancelled: Callable[[], bool] = lambda: False
    max_pages: int = 50_000
    max_bytes: int = 32 * 1024 * 1024
    timeout: float = 120.0
    started: float = field(default_factory=time.monotonic)
    pages: int = 0
    size: int = 0

    def check(self) -> None:
        if self.cancelled():
            raise CancelledError()
        if time.monotonic() - self.started >= self.timeout:
            raise ExtractionLimit("PDF extraction time budget exceeded.")

    def add_page(self, text: str) -> str:
        self.check()
        self.pages += 1
        self.size += len(text.encode("utf-8"))
        if self.pages > self.max_pages or self.size > self.max_bytes:
            raise ExtractionLimit("PDF extraction output budget exceeded.")
        return text


def bounded_text_process(command: list[str], budget: ExtractionBudget) -> str:
    """Spool output off heap, check during execution, always reap the child."""
    budget.check()
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen(command, stdout=output, stderr=subprocess.DEVNULL)
        try:
            while True:
                budget.check()
                if os.fstat(output.fileno()).st_size > budget.max_bytes:
                    raise ExtractionLimit("PDF extraction output budget exceeded.")
                try:
                    code = process.wait(timeout=0.05)
                    break
                except subprocess.TimeoutExpired:
                    continue
            budget.check()
            if os.fstat(output.fileno()).st_size > budget.max_bytes:
                raise ExtractionLimit("PDF extraction output budget exceeded.")
            if code:
                raise RuntimeError("PDF extraction process failed.")
            output.seek(0)
            return output.read(budget.max_bytes).decode("utf-8", errors="replace")
        finally:
            if process.poll() is None:
                process.kill()
            process.wait()
