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

from app.core.activity_log import log_activity
from app.models.user import Role, User
from app.web.middleware.auth import get_current_user_ws

logger = logging.getLogger(__name__)
router = APIRouter()


async def _fail(websocket: WebSocket, message: str, code: int = 4000) -> None:
    """Tell the client why, then close. A silent close reads as a network fault."""
    await websocket.send_json({"type": "output", "data": f"\r\n*** {message} ***\r\n"})
    await websocket.close(code=code, reason=message[:120])


async def _may_open_host(actor: User, host) -> bool:
    """Whether *actor* may reach this host. See ssh.py for the same rule."""
    from app.core.rbac import check_customer_access, get_accessible_customer_ids

    if host.customer_id:
        return await check_customer_access(actor, host.customer_id)
    return await get_accessible_customer_ids(actor) is None


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
        await _handle_ssh_terminal(websocket, user)
    else:
        log_activity(
            "terminal_local_opened",
            detail="Åpnet lokalt skall på hub-verten",
            user=user.username,
        )
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


async def _handle_ssh_terminal(websocket: WebSocket, actor: User):
    """SSH interactive session via asyncssh piped through WebSocket.

    ``actor`` is the authenticated hub user, as distinct from the ``user``
    local below, which is the SSH login name on the target host.
    """
    import asyncssh

    host_id = websocket.query_params.get("host_id", "")
    host = websocket.query_params.get("host", "")
    user = websocket.query_params.get("user", "root")
    try:
        port = int(websocket.query_params.get("port", "22") or "22")
    except ValueError:
        # The websocket is already accepted, so an unhandled ValueError here
        # closes the connection with no explanation at all.
        await websocket.send_json({"type": "output", "data": "\r\nUgyldig port.\r\n"})
        await websocket.close(code=4000, reason="Invalid port")
        return

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
        # Opening a shell on a host is the most invasive thing this product
        # does, and it resolves the host's stored credential to do it. Same
        # tenancy rule as every other route that touches a host.
        if not await _may_open_host(actor, h):
            logger.info(
                "403 host-access: user=%s host=%s customer=%s (terminal)",
                actor.username, host_id, h.customer_id,
            )
            await websocket.send_json({
                "type": "output",
                "data": "\r\n*** Tilgang nektet — du har ikke tilgang til denne hosten ***\r\n",
            })
            await websocket.close(code=4003, reason="No access to this host")
            return
        log_activity(
            "terminal_ssh_opened",
            detail=f"Åpnet SSH-økt mot {h.label or h.hostname} ({host_id})",
            customer=h.customer_id or "",
            user=actor.username,
        )
        host = h.hostname
        port = h.port
        user = h.username
        # A credential that will not load is a configuration fault to report,
        # not something to connect without. Continuing left asyncssh with
        # neither a password nor a key and the session died at the far end
        # with "Permission denied", which sends the technician looking at the
        # customer's host for a problem that is on this one.
        if h.auth_method == AuthMethod.password:
            password = _load_host_password(h.id)
            if not password:
                await _fail(websocket, "Passordet for denne hosten kunne ikke hentes "
                                       "— sjekk at det er lagret på nytt.")
                return
        elif h.auth_method == AuthMethod.key and h.auth_key_id:
            try:
                private_key = _load_private_key(h.auth_key_id)
            except (ValueError, OSError) as e:
                logger.warning("Failed to load private key %s for host %s: %s", h.auth_key_id, host_id, e)
                await _fail(websocket, "Nøkkelen for denne hosten kunne ikke leses.")
                return
    elif host:
        # An address typed straight into the query string belongs to no
        # customer, so nobody's access grant covers it — the same rule the
        # host branch applies to a host with no customer_id. This branch used
        # to run with no tenancy check and no activity entry at all: a shell
        # opened on an arbitrary address left no trace of who or where.
        from app.core.rbac import get_accessible_customer_ids

        if await get_accessible_customer_ids(actor) is not None:
            logger.info(
                "403 ad-hoc terminal: user=%s host=%s (restricted to specific customers)",
                actor.username, host,
            )
            await _fail(
                websocket,
                "Tilgang nektet — du kan bare åpne terminal mot hoster som er "
                "registrert på en kunde du har tilgang til.",
                code=4003,
            )
            return
        log_activity(
            "terminal_ssh_opened",
            detail=f"Åpnet SSH-økt mot ad hoc-adresse {user}@{host}:{port}",
            user=actor.username,
        )

    if not host:
        await websocket.send_json({"type": "output", "data": "\r\nIngen host angitt.\r\n"})
        await websocket.close()
        return

    await websocket.send_json({"type": "output", "data": f"Kobler til {user}@{host}:{port}...\r\n"})

    try:
        # known_hosts=None accepts any key, every time. This was the only call
        # site in the tree bypassing open_verified_connection, and it is the
        # one that carries a stored root password into an interactive session
        # — an on-path attacker inside the customer network could impersonate
        # the host and capture it. open_verified_connection pins on first use
        # and refuses a *changed* key, which is exactly the MITM signal.
        from app.services.ssh_connection import open_verified_connection

        # client_keys=None is load-bearing and is *not* the careless value it
        # looks like. asyncssh treats None as "offer nothing, and no agent
        # either"; an empty list or an omitted argument falls through to
        # load_default_keypairs(), which reads the hub's own ~/.ssh — so the
        # hub's identity would be offered to every customer device that
        # happened to trust it, unlogged and configured by nobody. Keep None.
        conn = await open_verified_connection(
            hostname=host,
            username=user,
            password=password or None,
            port=port,
            client_keys=[asyncssh.import_private_key(private_key)] if private_key else None,
            connect_timeout=15,
        )
        async with conn:
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
