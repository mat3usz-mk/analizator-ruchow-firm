"""Limit czasu na jedno źródło: po jego przekroczeniu kolejne zapytania HTTP od razu kończą się błędem,
więc źródło, które wisi albo ponawia zapytania do zablokowanej domeny, nie zatrzymuje całego cyklu."""
from __future__ import annotations

import time

_deadline: float | None = None


class Przekroczono(TimeoutError):
    pass


def start(seconds: float) -> None:
    global _deadline
    _deadline = time.time() + seconds


def stop() -> None:
    global _deadline
    _deadline = None


def check() -> None:
    if _deadline is not None and time.time() > _deadline:
        raise Przekroczono("przekroczony limit czasu źródła")


def left(default: float) -> float:
    """Timeout pojedynczego zapytania nie dłuższy niż czas pozostały do limitu."""
    if _deadline is None:
        return default
    return max(1.0, min(default, _deadline - time.time()))
