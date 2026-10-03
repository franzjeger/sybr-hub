"""Nonblocking Unix descriptors: readiness is not the same thing as EOF."""

import asyncio
import errno
import os


async def _ready(fd: int, *, write: bool = False) -> None:
    loop = asyncio.get_running_loop()
    future: asyncio.Future[None] = loop.create_future()

    def wake() -> None:
        if not future.done():
            future.set_result(None)

    add = loop.add_writer if write else loop.add_reader
    remove = loop.remove_writer if write else loop.remove_reader
    add(fd, wake)
    try:
        await future
    finally:
        remove(fd)


async def read_fd(fd: int, size: int = 4096) -> bytes:
    while True:
        try:
            return os.read(fd, size)
        except BlockingIOError:
            await _ready(fd)
        except OSError as exc:
            if exc.errno == errno.EIO:  # Linux PTY slave closed.
                return b""
            raise


async def write_fd(fd: int, data: bytes) -> None:
    remaining = memoryview(data)
    while remaining:
        try:
            count = os.write(fd, remaining)
            if count == 0:
                raise OSError("descriptor closed during write")
            remaining = remaining[count:]
        except BlockingIOError:
            await _ready(fd, write=True)
