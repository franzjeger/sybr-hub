"""Web terminal via WebSocket — local shell or SSH to managed hosts."""

from __future__ import annotations

import asyncio
import fcntl
import logging
import os
import pty
import signal
import struct
import termios
from typing import Optional

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from app.models.user import Role, User
from app.web.middleware.auth import get_current_user_ws

logger = logging.getLogger(__name__)
router = APIRouter()


@router.websocket("/ws/terminal")
async def terminal_websocket(
    websocket: WebSocket, user: User = Depends(get_current_user_ws)
):
    """Interactive terminal via WebSocket.

    Query params:
      - token: JWT for auth
      - mode: "local" (default) or "ssh"
      - host_id: SSH host ID (when mode=ssh)
      - host: direct hostname (when mode=ssh, no host_id)
      - user: SSH username (when mode=ssh with host param)
      - port: SSH port (default 22)

    Protocol:
      Client -> Server: {"type": "input", "data": "..."} or {"type": "resize", "cols": N, "rows": N}
      Server -> Client: {"type": "output", "data": "..."}
    """
    # Authentication happens in get_current_user_ws, before this body runs, so
    # `user` is always a real active account. There is deliberately no
    # first-run bypass: this route hands out a shell, and the previous
    # "no accounts yet means no token needed" branch made that shell
    # unauthenticated on exactly the fresh installs it was meant to help.
    await websocket.accept()

    mode = websocket.query_params.get("mode", "local")

    # Enforce role before accepting any payload. The role floor depends on the
    # mode, so it cannot move into the dependency.
    #
    # Use the Role enum's ordering (viewer < technician < admin). The old
    # check compared user.role to the string "admin" which worked by
    # accident (Role is a str subclass) but left SSH mode completely
    # unprotected — any viewer could open a shell on any registered host.
    required = Role.admin if mode != "ssh" else Role.technician
    if user.role < required:
        msg_no = ("lokal terminal krever admin-rolle" if mode != "ssh"
                  else "SSH krever teknisk-rolle eller høyere")
        await websocket.send_json({
            "type": "output",
            "data": f"\r\n*** Tilgang nektet — {msg_no} ***\r\n",
        })
        logger.info(
            "Terminal WS denied: user=%s role=%s mode=%s required=%s",
            user.username, user.role.value, mode, required.value,
        )
        await websocket.close(code=4003, reason=f"Requires {required.value}+ role")
        return

    if mode == "ssh":
        await _handle_ssh_terminal(websocket)
    else:
        await _handle_local_terminal(websocket)


async def _handle_local_terminal(websocket: WebSocket):
    """Spawn a local PTY shell and pipe through WebSocket."""
    master_fd, slave_fd = pty.openpty()

    # Spawn shell
    shell = os.environ.get("SHELL", "/bin/bash")
    pid = os.fork()
    if pid == 0:
        # Child process
        os.close(master_fd)
        os.setsid()
        fcntl.ioctl(slave_fd, termios.TIOCSCTTY, 0)
        os.dup2(slave_fd, 0)
        os.dup2(slave_fd, 1)
        os.dup2(slave_fd, 2)
        os.close(slave_fd)
        os.execvp(shell, [shell])

    # Parent process
    os.close(slave_fd)

    # Set non-blocking
    flag = fcntl.fcntl(master_fd, fcntl.F_GETFL)
    fcntl.fcntl(master_fd, fcntl.F_SETFL, flag | os.O_NONBLOCK)

    loop = asyncio.get_event_loop()

    async def read_output():
        while True:
            try:
                data = await loop.run_in_executor(None, lambda: os.read(master_fd, 4096))
                if not data:
                    break
                await websocket.send_json({"type": "output", "data": data.decode("utf-8", errors="replace")})
            except OSError:
                break
            except Exception as e:
                logger.debug("Local terminal read error: %s", e)
                break

    read_task = asyncio.create_task(read_output())

    try:
        while True:
            msg = await websocket.receive_json()
            if msg.get("type") == "input":
                data = msg.get("data", "")
                os.write(master_fd, data.encode("utf-8"))
            elif msg.get("type") == "resize":
                cols = msg.get("cols", 80)
                rows = msg.get("rows", 24)
                winsize = struct.pack("HHHH", rows, cols, 0, 0)
                fcntl.ioctl(master_fd, termios.TIOCSWINSZ, winsize)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("Terminal WS error: %s", e)
    finally:
        read_task.cancel()
        os.close(master_fd)
        try:
            os.kill(pid, signal.SIGTERM)
            os.waitpid(pid, 0)
        except OSError as e:
            logger.debug("Failed to terminate shell process %d: %s", pid, e)


async def _handle_ssh_terminal(websocket: WebSocket):
    """SSH interactive session via asyncssh piped through WebSocket."""
    import asyncssh

    host_id = websocket.query_params.get("host_id", "")
    host = websocket.query_params.get("host", "")
    user = websocket.query_params.get("user", "root")
    port = int(websocket.query_params.get("port", "22"))

    # Resolve host from database if host_id provided
    password = None
    private_key = None
    if host_id:
        from app.models.ssh import AuthMethod
        from app.services.ssh_manager import _load_host_password, _load_private_key, get_host
        h = await get_host(host_id)
        if not h:
            await websocket.send_json({"type": "output", "data": f"\r\nHost {host_id} ikke funnet.\r\n"})
            await websocket.close()
            return
        host = h.hostname
        port = h.port
        user = h.username
        if h.auth_method == AuthMethod.password:
            password = _load_host_password(h.id)
        elif h.auth_method == AuthMethod.key and h.auth_key_id:
            try:
                private_key = _load_private_key(h.auth_key_id)
            except (ValueError, OSError) as e:
                logger.warning("Failed to load private key %s for host %s: %s", h.auth_key_id, host_id, e)

    if not host:
        await websocket.send_json({"type": "output", "data": "\r\nIngen host angitt.\r\n"})
        await websocket.close()
        return

    await websocket.send_json({"type": "output", "data": f"Kobler til {user}@{host}:{port}...\r\n"})

    try:
        kwargs = {
            "host": host, "port": port, "username": user,
            "known_hosts": None, "connect_timeout": 15,
        }
        if private_key:
            kwargs["client_keys"] = [asyncssh.import_private_key(private_key)]
        if password:
            kwargs["password"] = password

        async with asyncssh.connect(**kwargs) as conn:
            # Open interactive shell with PTY
            stdin, stdout, stderr = await conn.open_session(
                term_type="xterm-256color",
                term_size=(80, 24),
            )

            await websocket.send_json({"type": "output", "data": f"Tilkoblet {host}.\r\n"})

            async def read_stdout():
                try:
                    while True:
                        data = await stdout.read(4096)
                        if not data:
                            break
                        await websocket.send_json({"type": "output", "data": data})
                except asyncssh.BreakReceived:
                    pass
                except Exception as e:
                    logger.debug("SSH stdout read error for %s: %s", host, e)

            async def read_stderr():
                try:
                    while True:
                        data = await stderr.read(4096)
                        if not data:
                            break
                        await websocket.send_json({"type": "output", "data": data})
                except Exception as e:
                    logger.debug("SSH stderr read error for %s: %s", host, e)

            read_task1 = asyncio.create_task(read_stdout())
            read_task2 = asyncio.create_task(read_stderr())

            try:
                while True:
                    msg = await websocket.receive_json()
                    if msg.get("type") == "input":
                        stdin.write(msg.get("data", ""))
                    elif msg.get("type") == "resize":
                        stdin.channel.change_terminal_size(
                            msg.get("cols", 80), msg.get("rows", 24)
                        )
            except WebSocketDisconnect:
                pass
            finally:
                read_task1.cancel()
                read_task2.cancel()
                stdin.close()

    except asyncssh.Error as e:
        try:
            await websocket.send_json({"type": "output", "data": f"\r\nSSH-feil: {e}\r\n"})
        except (WebSocketDisconnect, RuntimeError) as e2:
            logger.debug("Failed to send SSH error to WebSocket: %s", e2)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.warning("Unexpected SSH terminal error for %s: %s", host, e)
        try:
            await websocket.send_json({"type": "output", "data": f"\r\nFeil: {e}\r\n"})
        except (WebSocketDisconnect, RuntimeError) as e2:
            logger.debug("Failed to send error to WebSocket: %s", e2)
