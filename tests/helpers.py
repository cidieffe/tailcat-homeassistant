"""Shared fakes standing in for a real tailcat subprocess in tests."""
from __future__ import annotations

import asyncio


class FakeStream:
    """A minimal stand-in for asyncio.StreamReader."""

    def __init__(self, lines: list[bytes]) -> None:
        self._lines = list(lines)
        self._blocked = asyncio.Event()

    async def readline(self) -> bytes:
        if self._lines:
            return self._lines.pop(0)
        await self._blocked.wait()
        return b""

    def unblock(self) -> None:
        self._blocked.set()


class FakeProcess:
    """A minimal stand-in for asyncio.subprocess.Process."""

    def __init__(self, stderr_lines: list[bytes] | None = None) -> None:
        self.stdout = FakeStream([])
        self.stderr = FakeStream(stderr_lines or [])
        self._exited = asyncio.Event()
        self.returncode: int | None = None
        self.terminated = False

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0
        self.stdout.unblock()
        self.stderr.unblock()
        self._exited.set()

    def kill(self) -> None:
        self.terminate()

    async def wait(self) -> int:
        await self._exited.wait()
        return self.returncode
