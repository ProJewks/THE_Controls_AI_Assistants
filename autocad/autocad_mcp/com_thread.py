"""
Runs all AutoCAD COM calls on one dedicated background thread.

COM objects are apartment-threaded (STA): a COM pointer obtained on one
thread cannot safely be called from another thread. An MCP server's tool
handlers can be invoked from whatever thread the async runtime picks, so
every AutoCAD call is funneled through a single persistent worker thread
that owns the COM apartment and the cached Application/Document pointers.
"""

from __future__ import annotations

import queue
import threading
from concurrent.futures import Future
from typing import Callable, TypeVar

import pythoncom

T = TypeVar("T")


class ComThread:
    def __init__(self) -> None:
        self._queue: "queue.Queue[tuple[Callable, Future]]" = queue.Queue()
        self._thread = threading.Thread(
            target=self._run, name="autocad-com", daemon=True
        )
        self._thread.start()

    def _run(self) -> None:
        pythoncom.CoInitialize()
        try:
            while True:
                fn, fut = self._queue.get()
                if not fut.set_running_or_notify_cancel():
                    continue
                try:
                    fut.set_result(fn())
                except BaseException as exc:  # noqa: BLE001
                    fut.set_exception(exc)
        finally:
            pythoncom.CoUninitialize()

    def run(self, fn: Callable[[], T], timeout: float = 60.0) -> T:
        fut: Future = Future()
        self._queue.put((fn, fut))
        return fut.result(timeout=timeout)


_com_thread = ComThread()


def run(fn: Callable[[], T], timeout: float = 60.0) -> T:
    return _com_thread.run(fn, timeout=timeout)
