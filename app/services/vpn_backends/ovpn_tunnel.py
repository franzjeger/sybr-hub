"""Pure Python OpenVPN tunnel for Azure P2S VPN.

Implements the OpenVPN wire protocol over TCP with tls-auth,
Key Method 2, and AES-256-GCM data channel — no openvpn binary needed.
"""

import asyncio
import fcntl
import hmac as _hmac
import logging
import os
import socket
import ssl
import struct
import time
from typing import Optional

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.hmac import HMAC
from OpenSSL import SSL as _ossl
from OpenSSL import crypto as _ocrypto

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# OpenVPN opcodes (high 5 bits of first byte)
# ---------------------------------------------------------------------------
P_CONTROL_HARD_RESET_CLIENT_V2 = 7
P_CONTROL_HARD_RESET_SERVER_V2 = 8
P_CONTROL_V1 = 4
P_ACK_V1 = 5
P_DATA_V1 = 6
P_DATA_V2 = 9

P_OPCODE_SHIFT = 3
P_KEY_ID_MASK = 0x07

SID_SIZE = 8  # session ID length

# Linux TUN constants
TUNSETIFF = 0x400454CA
IFF_TUN = 0x0001
IFF_NO_PI = 0x1000

# OpenVPN keepalive ping payload
PING_PAYLOAD = bytes([
    0x2A, 0x18, 0x7B, 0xF3, 0x64, 0x1E, 0xB4, 0xCB,
    0x07, 0xED, 0x2D, 0x0A, 0x98, 0x1F, 0xC7, 0x48,
])

# Max control payload per packet (leave room for headers within TLS MTU)
MAX_CONTROL_PAYLOAD = 1200

# Module-level tunnel reference (duck-types openvpn._PROCESS)
_TUNNEL: Optional["OpenVPNTunnel"] = None


# ---------------------------------------------------------------------------
# tls-auth static key parsing
# ---------------------------------------------------------------------------

def parse_tls_auth_key(hex_str: str) -> tuple[bytes, bytes]:
    """Parse 512-char hex string into (hmac_send_key, hmac_recv_key) for direction 1 (client).

    The 256-byte static key is split into 4 x 64-byte regions:
      [0:64]    = encrypt cipher key   (direction 0 send / direction 1 recv)
      [64:128]  = HMAC key             (direction 0 send / direction 1 recv)
      [128:192] = encrypt cipher key   (direction 1 send / direction 0 recv)
      [192:256] = HMAC key             (direction 1 send / direction 0 recv)

    For direction 1 (client):
      hmac_send = bytes[192:256]
      hmac_recv = bytes[64:128]
    """
    raw = bytes.fromhex(hex_str)
    # Explicit check rather than `assert` — this validates user-supplied key
    # material and must survive `python -O` (which strips asserts).
    if len(raw) != 256:
        raise ValueError(f"tls-auth key must be 256 bytes, got {len(raw)}")
    hmac_send = raw[192:256]  # client -> server
    hmac_recv = raw[64:128]   # server -> client
    return hmac_send, hmac_recv


# ---------------------------------------------------------------------------
# TUN device
# ---------------------------------------------------------------------------

class TunDevice:
    """Linux TUN device via /dev/net/tun.

    Uses a sudo helper to create the TUN fd, then passes it back to the
    unprivileged process so all data I/O stays in userspace.
    """

    def __init__(self, name: str = "tun0"):
        self.name = name
        self._fd: Optional[int] = None

    async def open(self) -> int:
        """Open TUN device. Cleans up stale interface first, then tries direct or sudo."""
        # Clean up any stale tun device from a previous session
        await self._delete_interface()
        try:
            self._fd = self._open_direct()
        except PermissionError:
            logger.debug("Direct TUN open failed, using sudo helper")
            self._fd = await self._open_via_sudo()
        logger.info("TUN device %s opened (fd=%d)", self.name, self._fd)
        return self._fd

    async def _delete_interface(self):
        """Delete the TUN interface if it exists."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "sudo", "ip", "link", "delete", self.name,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            await asyncio.wait_for(proc.communicate(), 5)
        except Exception:
            pass

    def _open_direct(self) -> int:
        """Try opening TUN directly (works if we have CAP_NET_ADMIN)."""
        fd = os.open("/dev/net/tun", os.O_RDWR)
        ifr = struct.pack("16sH22s", self.name.encode(), IFF_TUN | IFF_NO_PI, b"\x00" * 22)
        fcntl.ioctl(fd, TUNSETIFF, ifr)
        return fd

    async def _open_via_sudo(self) -> int:
        """Open TUN via sudo python helper, receive fd over named Unix socket."""
        import tempfile

        sock_path = tempfile.mktemp(suffix=".sock", prefix="msp-tun-")

        # Write helper script (runs as root, connects to our socket, sends TUN fd)
        helper_code = (
            "import os, socket, struct, fcntl, sys\n"
            "TUNSETIFF = 0x400454CA\n"
            "fd = os.open('/dev/net/tun', os.O_RDWR)\n"
            "ifr = struct.pack('16sH', sys.argv[2].encode(), 0x0001 | 0x1000) + bytes(22)\n"
            "fcntl.ioctl(fd, TUNSETIFF, ifr)\n"
            "sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)\n"
            "sock.connect(sys.argv[1])\n"
            "sock.sendmsg([b'ok'], [(socket.SOL_SOCKET, socket.SCM_RIGHTS, struct.pack('i', fd))])\n"
            "sock.close()\n"
            "os.close(fd)\n"
        )
        helper_file = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False)
        helper_file.write(helper_code)
        helper_file.close()

        # Create listening Unix socket
        server_sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server_sock.bind(sock_path)
        server_sock.listen(1)

        try:
            proc = await asyncio.create_subprocess_exec(
                "sudo", "python3", helper_file.name, sock_path, self.name,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)

            # Accept connection from helper
            loop = asyncio.get_event_loop()
            conn, _ = await loop.run_in_executor(None, server_sock.accept)
            msg, ancdata, flags, addr = conn.recvmsg(16, socket.CMSG_SPACE(struct.calcsize("i")))
            conn.close()

            for cmsg_level, cmsg_type, cmsg_data in ancdata:
                if cmsg_level == socket.SOL_SOCKET and cmsg_type == socket.SCM_RIGHTS:
                    fd = struct.unpack("i", cmsg_data[:4])[0]
                    await proc.wait()
                    return fd

            raise PermissionError("Fikk ikke TUN fd fra sudo helper")
        except PermissionError:
            raise
        except Exception as e:
            _, stderr = await proc.communicate()
            raise PermissionError(
                f"Kunne ikke opprette TUN-enhet: {stderr.decode().strip() or e}") from e
        finally:
            server_sock.close()
            try:
                os.unlink(sock_path)
            except OSError:
                pass
            try:
                os.unlink(helper_file.name)
            except OSError:
                pass

    async def configure(self, local_ip: str, netmask_or_peer: str, mtu: int = 1500):
        # Detect if second value is a netmask (subnet topology) or peer IP (net30)
        parts = netmask_or_peer.split(".")
        if len(parts) == 4 and int(parts[0]) >= 224:
            # It's a netmask like 255.255.255.0 — convert to prefix
            prefix = sum(bin(int(x)).count("1") for x in parts)
            addr_cmd = ["sudo", "ip", "addr", "add", f"{local_ip}/{prefix}", "dev", self.name]
        else:
            # It's a peer IP (net30 topology)
            addr_cmd = ["sudo", "ip", "addr", "add", f"{local_ip}/32", "peer", netmask_or_peer, "dev", self.name]
        cmds = [
            addr_cmd,
            ["sudo", "ip", "link", "set", self.name, "up"],
            ["sudo", "ip", "link", "set", self.name, "mtu", str(mtu)],
        ]
        for cmd in cmds:
            proc = await asyncio.create_subprocess_exec(
                *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
            _, stderr = await asyncio.wait_for(proc.communicate(), 5)
            if proc.returncode != 0:
                logger.warning("TUN configure %s: %s", " ".join(cmd), stderr.decode().strip())

    async def add_route(self, network: str, netmask_or_prefix: str):
        """Add a route via this TUN device."""
        # Convert dotted netmask to prefix if needed
        if "." in netmask_or_prefix:
            prefix = sum(bin(int(x)).count("1") for x in netmask_or_prefix.split("."))
        else:
            prefix = int(netmask_or_prefix)
        cmd = ["sudo", "ip", "route", "add", f"{network}/{prefix}", "dev", self.name]
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        await asyncio.wait_for(proc.communicate(), 5)

    def close(self):
        if self._fd is not None:
            try:
                os.close(self._fd)
            except OSError:
                pass
            self._fd = None
            logger.info("TUN device %s closed", self.name)

    def fileno(self) -> int:
        if self._fd is None:
            raise RuntimeError("TUN device not opened — call .open() first")
        return self._fd


# ---------------------------------------------------------------------------
# Reliability layer
# ---------------------------------------------------------------------------

class ReliableLayer:
    """Control channel reliability: ordering, ACKs, retransmission."""

    def __init__(self):
        self._send_id = 0          # next outgoing msg_packet_id
        self._recv_expected = 0    # next expected incoming msg_packet_id
        self._pending_acks: list[int] = []
        self._unacked: dict[int, tuple[float, bytes]] = {}  # id -> (timestamp, raw_packet)
        self._recv_buffer: dict[int, bytes] = {}  # out-of-order buffer

    def next_send_id(self) -> int:
        pid = self._send_id
        self._send_id += 1
        return pid

    def record_sent(self, packet_id: int, raw_packet: bytes):
        self._unacked[packet_id] = (time.monotonic(), raw_packet)

    def ack_received(self, ack_ids: list[int]):
        for aid in ack_ids:
            self._unacked.pop(aid, None)

    def data_received(self, packet_id: int, payload: bytes) -> list[bytes]:
        """Process incoming packet, return ordered payloads ready for delivery."""
        self._pending_acks.append(packet_id)

        if packet_id == self._recv_expected:
            # In-order: deliver this and any buffered consecutive packets
            result = [payload]
            self._recv_expected += 1
            while self._recv_expected in self._recv_buffer:
                result.append(self._recv_buffer.pop(self._recv_expected))
                self._recv_expected += 1
            return result
        elif packet_id > self._recv_expected:
            # Out-of-order: buffer
            self._recv_buffer[packet_id] = payload
        # Duplicate or old: ignore
        return []

    def get_pending_acks(self) -> list[int]:
        acks = self._pending_acks[:8]  # max 8 per packet
        self._pending_acks = self._pending_acks[8:]
        return acks

    def get_retransmits(self, timeout: float = 2.0) -> list[bytes]:
        """Return raw packets that haven't been ACKed within timeout."""
        now = time.monotonic()
        result = []
        for pid, (ts, raw) in list(self._unacked.items()):
            if now - ts > timeout:
                result.append(raw)
                self._unacked[pid] = (now, raw)  # reset timer
        return result


# ---------------------------------------------------------------------------
# Control channel (tls-auth HMAC)
# ---------------------------------------------------------------------------

class ControlChannel:
    """Builds and parses OpenVPN control packets with tls-auth HMAC (SHA-256)."""

    HMAC_LEN = 32  # SHA-256

    def __init__(self, session_id: bytes, hmac_send_key: bytes, hmac_recv_key: bytes):
        self.session_id = session_id
        self.hmac_send_key = hmac_send_key[:32]  # SHA-256 uses 32 bytes
        self.hmac_recv_key = hmac_recv_key[:32]
        self._hmac_send_id = 0  # pre-incremented like OpenVPN: first used value is 1
        self._hmac_recv_id = 0

    def _compute_hmac(self, key: bytes, data: bytes) -> bytes:
        h = HMAC(key, hashes.SHA256())
        h.update(data)
        return h.finalize()

    def build_packet(
        self,
        opcode: int,
        key_id: int,
        payload: bytes,
        ack_ids: list[int],
        peer_sid: bytes,
        msg_packet_id: Optional[int] = None,
    ) -> bytes:
        """Build a control packet with tls-auth HMAC."""
        opcode_byte = ((opcode << P_OPCODE_SHIFT) | (key_id & P_KEY_ID_MASK)).to_bytes(1, "big")

        # Build the inner content (after HMAC region)
        ack_section = struct.pack("B", len(ack_ids))
        for aid in ack_ids:
            ack_section += struct.pack("!I", aid)
        if len(ack_ids) > 0 and peer_sid:
            ack_section += peer_sid

        body = ack_section
        if msg_packet_id is not None:
            body += struct.pack("!I", msg_packet_id)
        body += payload

        # HMAC covers: packet_id(4) + timestamp(4) + opcode(1) + session_id(8) + body
        self._hmac_send_id += 1  # pre-increment like OpenVPN (first value = 1)
        pkt_id = self._hmac_send_id
        ts = int(time.time())
        hmac_content = struct.pack("!II", pkt_id, ts) + opcode_byte + self.session_id + body
        hmac_val = self._compute_hmac(self.hmac_send_key, hmac_content)

        # Wire format: opcode | session_id | HMAC | packet_id | timestamp | body
        packet = opcode_byte + self.session_id + hmac_val + struct.pack("!II", pkt_id, ts) + body
        return packet

    def parse_packet(self, data: bytes) -> Optional[dict]:
        """Parse a control packet, verify HMAC. Returns dict or None if invalid."""
        if len(data) < 1 + SID_SIZE + self.HMAC_LEN + 8 + 1:
            return None

        pos = 0
        opcode_byte = data[pos]; pos += 1
        opcode = (opcode_byte >> P_OPCODE_SHIFT) & 0x1F
        key_id = opcode_byte & P_KEY_ID_MASK

        session_id = data[pos:pos + SID_SIZE]; pos += SID_SIZE
        hmac_val = data[pos:pos + self.HMAC_LEN]; pos += self.HMAC_LEN
        pkt_id, ts = struct.unpack_from("!II", data, pos); pos += 8

        # Verify HMAC
        hmac_content = struct.pack("!II", pkt_id, ts) + data[0:1] + session_id + data[pos:]
        expected = self._compute_hmac(self.hmac_recv_key, hmac_content)
        if not _hmac.compare_digest(hmac_val, expected):
            logger.warning("HMAC verification failed for opcode %d", opcode)
            return None

        # Parse ACK section
        ack_len = data[pos]; pos += 1
        ack_ids = []
        for _ in range(ack_len):
            ack_ids.append(struct.unpack_from("!I", data, pos)[0]); pos += 4
        peer_sid = b""
        if ack_len > 0:
            peer_sid = data[pos:pos + SID_SIZE]; pos += SID_SIZE

        # msg_packet_id (absent for P_ACK_V1)
        msg_packet_id = None
        if opcode != P_ACK_V1 and pos + 4 <= len(data):
            msg_packet_id = struct.unpack_from("!I", data, pos)[0]; pos += 4

        payload = data[pos:]

        return {
            "opcode": opcode,
            "key_id": key_id,
            "session_id": session_id,
            "ack_ids": ack_ids,
            "peer_sid": peer_sid,
            "msg_packet_id": msg_packet_id,
            "payload": payload,
        }


# ---------------------------------------------------------------------------
# Data channel (P_DATA_V2 with AES-256-GCM)
# ---------------------------------------------------------------------------

class DataChannel:
    """Encrypts/decrypts OpenVPN data packets with AES-256-GCM.

    Uses P_DATA_V1 (opcode 6) when no peer-id is assigned,
    or P_DATA_V2 (opcode 9) when the server pushes a peer-id.
    """

    def __init__(
        self,
        key_encrypt: bytes,
        key_decrypt: bytes,
        iv_encrypt: bytes,
        iv_decrypt: bytes,
        peer_id: int,
        key_id: int = 0,
    ):
        self._enc = AESGCM(key_encrypt)
        self._dec = AESGCM(key_decrypt)
        self._iv_encrypt = iv_encrypt  # 12 bytes implicit IV
        self._iv_decrypt = iv_decrypt
        self._peer_id = peer_id
        self._key_id = key_id
        self._send_pkt_id = 1  # data channel starts at 1 (like OpenVPN)
        self._recv_pkt_id = 0
        # Use V2 only if server assigned a peer-id, otherwise V1
        self._use_v2 = peer_id > 0

    def _make_nonce(self, packet_id: int, implicit_iv: bytes) -> bytes:
        """Build 12-byte GCM nonce: implicit_iv(12) XOR packet_id into first 4 bytes.

        OpenVPN AEAD nonce (from crypto.c openvpn_encrypt_aead):
          memcpy(iv, implicit_iv, 12)
          iv[0:4] ^= packet_id(4 bytes big-endian)
        """
        nonce = bytearray(implicit_iv[0:12])
        pid_bytes = struct.pack("!I", packet_id)
        for i in range(4):
            nonce[i] ^= pid_bytes[i]
        return bytes(nonce)

    def encrypt(self, plaintext: bytes) -> bytes:
        """Encrypt a TUN packet into a data channel frame."""
        pkt_id = self._send_pkt_id
        self._send_pkt_id += 1
        pkt_id_bytes = struct.pack("!I", pkt_id)
        nonce = self._make_nonce(pkt_id, self._iv_encrypt)

        if self._use_v2:
            # P_DATA_V2: header(4) = opcode(1) + peer_id(3)
            opcode_byte = ((P_DATA_V2 << P_OPCODE_SHIFT) | (self._key_id & P_KEY_ID_MASK)).to_bytes(1, "big")
            header = opcode_byte + struct.pack("!I", self._peer_id)[1:]
        else:
            # P_DATA_V1: header(1) = opcode byte only
            header = ((P_DATA_V1 << P_OPCODE_SHIFT) | (self._key_id & P_KEY_ID_MASK)).to_bytes(1, "big")

        # AAD = header + packet_id
        aad = header + pkt_id_bytes
        ct_and_tag = self._enc.encrypt(nonce, plaintext, aad)
        ciphertext = ct_and_tag[:-16]
        tag = ct_and_tag[-16:]

        # Wire: header + pkt_id(4) + tag(16) + ciphertext
        return header + pkt_id_bytes + tag + ciphertext

    def decrypt(self, data: bytes) -> Optional[bytes]:
        """Decrypt a data channel frame (V1 or V2), return plaintext or None."""
        opcode = (data[0] >> P_OPCODE_SHIFT) & 0x1F
        if opcode == P_DATA_V2:
            header = data[:4]  # opcode(1) + peer_id(3)
            rest = data[4:]
        else:
            header = data[:1]  # P_DATA_V1: opcode(1) only
            rest = data[1:]

        if len(rest) < 4 + 16:
            return None
        pkt_id_bytes = rest[:4]
        pkt_id = struct.unpack("!I", pkt_id_bytes)[0]
        tag = rest[4:20]
        ciphertext = rest[20:]

        nonce = self._make_nonce(pkt_id, self._iv_decrypt)
        aad = header + pkt_id_bytes
        ct_and_tag = ciphertext + tag
        try:
            return self._dec.decrypt(nonce, ct_and_tag, aad)
        except Exception:
            logger.debug("Data channel decrypt failed for pkt_id=%d", pkt_id)
            return None


# ---------------------------------------------------------------------------
# OpenVPN PRF (key derivation)
# ---------------------------------------------------------------------------

def _openvpn_prf(secret: bytes, label: bytes, seed: bytes, length: int) -> bytes:
    """TLS 1.0-style PRF with HMAC-SHA256.

    P_hash(secret, seed) = HMAC(secret, A(1) + seed) + HMAC(secret, A(2) + seed) + ...
    where A(0) = seed, A(i) = HMAC(secret, A(i-1))
    """
    label_seed = label + seed
    result = b""
    a = label_seed  # A(0)
    while len(result) < length:
        h = HMAC(secret, hashes.SHA256())
        h.update(a)
        a = h.finalize()  # A(i)

        h2 = HMAC(secret, hashes.SHA256())
        h2.update(a + label_seed)
        result += h2.finalize()
    return result[:length]


def derive_keys(
    pre_master: bytes,
    client_random1: bytes,
    server_random1: bytes,
    client_random2: bytes,
    server_random2: bytes,
    client_sid: bytes = b"",
    server_sid: bytes = b"",
) -> dict:
    """Derive data channel keys using OpenVPN PRF.

    The key expansion seed includes session IDs (client_sid + server_sid).
    Key layout from PRF output (256 bytes = 2 x struct key):
      keys[0].cipher = [0:64], keys[0].hmac = [64:128]
      keys[1].cipher = [128:192], keys[1].hmac = [192:256]

    With tls-auth direction 1 (client):
      encrypt = keys[1], decrypt = keys[0]
    """
    master = _openvpn_prf(
        pre_master,
        b"OpenVPN master secret",
        client_random1 + server_random1,
        48,
    )
    # Key expansion includes session IDs in the seed
    expanded = _openvpn_prf(
        master,
        b"OpenVPN key expansion",
        client_random2 + server_random2 + client_sid + server_sid,
        256,
    )
    # Direction 1 (client, keydir 1): encrypt=keys[1], decrypt=keys[0]
    # Implicit IV is 12 bytes (GCM nonce length), taken from start of hmac section
    return {
        "client_cipher_key": expanded[128:160],    # keys[1].cipher[:32]
        "server_cipher_key": expanded[0:32],       # keys[0].cipher[:32]
        "client_implicit_iv": expanded[192:204],   # keys[1].hmac[:12]
        "server_implicit_iv": expanded[64:76],     # keys[0].hmac[:12]
    }


def derive_keys_ekm(ssl_obj: ssl.SSLObject) -> dict:
    """Derive data channel keys using TLS Exported Keying Material (RFC 5705)."""
    material = ssl_obj.export_keying_material(
        "EXPORTER-OpenVPN-datakeys", 256, None
    )
    # Same layout as PRF: keys[0] then keys[1], each 128 bytes (cipher:64 + hmac:64)
    # Direction 1: encrypt=keys[1], decrypt=keys[0], implicit_iv=8 bytes
    return {
        "client_cipher_key": material[128:160],
        "server_cipher_key": material[0:32],
        "client_implicit_iv": material[192:200],
        "server_implicit_iv": material[64:72],
    }


# ---------------------------------------------------------------------------
# Key Method 2 message construction / parsing
# ---------------------------------------------------------------------------

def build_key_method_2(
    pre_master: bytes,
    random1: bytes,
    random2: bytes,
    options: str,
    username: str,
    password: str,
    peer_info: str,
) -> bytes:
    """Build the client's Key Method 2 message."""
    msg = b"\x00\x00\x00\x00"  # literal zeros
    msg += b"\x02"              # key method 2
    msg += pre_master            # 48 bytes
    msg += random1               # 32 bytes
    msg += random2               # 32 bytes

    # Each string field: uint16 BE length (includes null terminator) + null-terminated string
    for s in (options, username, password, peer_info):
        encoded = s.encode("utf-8") + b"\x00"
        msg += struct.pack("!H", len(encoded))
        msg += encoded

    return msg


def parse_key_method_2_server(data: bytes) -> dict:
    """Parse the server's Key Method 2 response.

    Server format: [4 zeros][key_method(1)][random1(32)][random2(32)][options...]
    NOTE: Server sends 4-byte zero prefix + key_method, but NO pre_master.
    """
    pos = 0
    pos += 5  # 4 bytes zeros + 1 byte key_method
    # Server sends only random1 + random2, NO pre_master
    random1 = data[pos:pos + 32]; pos += 32
    random2 = data[pos:pos + 32]; pos += 32

    # Options string
    options_len = struct.unpack_from("!H", data, pos)[0]; pos += 2
    options = data[pos:pos + options_len].rstrip(b"\x00").decode("utf-8", errors="replace")
    pos += options_len

    return {
        "random1": random1,
        "random2": random2,
        "options": options,
    }


# ---------------------------------------------------------------------------
# PUSH_REPLY parsing
# ---------------------------------------------------------------------------

def parse_push_reply(reply: str) -> dict:
    """Parse PUSH_REPLY comma-separated directives."""
    result = {
        "ifconfig_local": "",
        "ifconfig_remote": "",
        "peer_id": 0,
        "routes": [],
        "dns_servers": [],
        "cipher": "AES-256-GCM",
        "ping": 10,
        "ping_restart": 120,
        "use_ekm": False,
    }
    parts = reply.split(",")
    for part in parts:
        part = part.strip()
        tokens = part.split()
        if not tokens:
            continue
        directive = tokens[0]
        if directive == "ifconfig" and len(tokens) >= 3:
            result["ifconfig_local"] = tokens[1]
            result["ifconfig_remote"] = tokens[2]
        elif directive == "route" and len(tokens) >= 3:
            result["routes"].append((tokens[1], tokens[2]))
        elif directive == "peer-id" and len(tokens) >= 2:
            result["peer_id"] = int(tokens[1])
        elif directive == "cipher" and len(tokens) >= 2:
            result["cipher"] = tokens[1]
        elif directive == "ping" and len(tokens) >= 2:
            result["ping"] = int(tokens[1])
        elif directive == "ping-restart" and len(tokens) >= 2:
            result["ping_restart"] = int(tokens[1])
        elif directive == "dhcp-option" and len(tokens) >= 3 and tokens[1] == "DNS":
            result["dns_servers"].append(tokens[2])
        elif directive == "protocol-flags":
            if "tls-ekm" in tokens:
                result["use_ekm"] = True
        elif directive == "key-derivation" and len(tokens) >= 2:
            if tokens[1] == "tls-ekm":
                result["use_ekm"] = True
    return result


# ---------------------------------------------------------------------------
# OpenVPNTunnel — main orchestrator
# ---------------------------------------------------------------------------

class OpenVPNTunnel:
    """Pure Python OpenVPN tunnel for Azure P2S VPN."""

    def __init__(
        self,
        gateway: str,
        ca_cert: str,
        tls_auth_key_hex: str,
        access_token: str,
        routes: Optional[list] = None,
        dns_servers: Optional[list] = None,
    ):
        self.gateway = gateway
        self.ca_cert = ca_cert
        self.tls_auth_key_hex = tls_auth_key_hex
        self.access_token = access_token
        self.routes = routes or []
        self.dns_servers = dns_servers or []

        self._running = False
        self._reader: Optional[asyncio.StreamReader] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._tun: Optional[TunDevice] = None
        self._data_channel: Optional[DataChannel] = None
        self._ossl_conn: Optional[_ossl.Connection] = None
        self._control: Optional[ControlChannel] = None
        self._reliable: Optional[ReliableLayer] = None
        self._peer_sid = b""
        self._session_id = b""
        self._key_id = 0

        self._tasks: list[asyncio.Task] = []
        self._last_recv_time = 0.0

    # -- Duck-type asyncio.subprocess.Process for openvpn._PROCESS compat --

    @property
    def returncode(self):
        return None if self._running else 1

    @property
    def pid(self):
        return os.getpid()

    def terminate(self):
        self._running = False

    def kill(self):
        self._running = False

    # -- TCP framing helpers --

    async def _tcp_send(self, data: bytes):
        """Send a length-prefixed packet over TCP."""
        frame = struct.pack("!H", len(data)) + data
        opcode = (data[0] >> P_OPCODE_SHIFT) & 0x1F if data else -1
        logger.debug("TCP SEND: opcode=%d len=%d hex=%s", opcode, len(data), data[:64].hex())
        self._writer.write(frame)
        await self._writer.drain()

    async def _tcp_recv(self) -> bytes:
        """Receive a length-prefixed packet from TCP."""
        length_bytes = await self._reader.readexactly(2)
        length = struct.unpack("!H", length_bytes)[0]
        return await self._reader.readexactly(length)

    # -- Control channel helpers --

    async def _send_control(self, opcode: int, payload: bytes = b"",
                            msg_packet_id: Optional[int] = None):
        """Build and send a control packet, record for retransmission."""
        ack_ids = self._reliable.get_pending_acks()
        pkt = self._control.build_packet(
            opcode, self._key_id, payload, ack_ids, self._peer_sid, msg_packet_id)
        if msg_packet_id is not None:
            self._reliable.record_sent(msg_packet_id, pkt)
        await self._tcp_send(pkt)

    async def _send_ack(self):
        """Send a standalone ACK packet."""
        ack_ids = self._reliable.get_pending_acks()
        if ack_ids:
            pkt = self._control.build_packet(
                P_ACK_V1, self._key_id, b"", ack_ids, self._peer_sid)
            await self._tcp_send(pkt)

    async def _recv_control(self) -> dict:
        """Receive and parse a control packet."""
        while True:
            data = await self._tcp_recv()
            opcode = (data[0] >> P_OPCODE_SHIFT) & 0x1F
            logger.debug("TCP RECV: opcode=%d len=%d", opcode, len(data))
            if opcode in (P_DATA_V1, P_DATA_V2):
                continue  # skip data packets during handshake
            parsed = self._control.parse_packet(data)
            if parsed is None:
                logger.warning("Failed to parse control packet (opcode=%d, len=%d)", opcode, len(data))
                continue
            # Process ACKs from this packet
            self._reliable.ack_received(parsed["ack_ids"])
            logger.debug("Control: opcode=%d acks=%s msg_id=%s payload_len=%d",
                         parsed["opcode"], parsed["ack_ids"],
                         parsed["msg_packet_id"], len(parsed["payload"]))
            return parsed

    # -- TLS over control channel --

    def _flush_tls_output(self) -> list[bytes]:
        """Read pending TLS output and split into control payload chunks."""
        try:
            out = self._ossl_conn.bio_read(65536)
        except _ossl.Error:
            out = b""
        if not out:
            return []
        chunks = []
        for i in range(0, len(out), MAX_CONTROL_PAYLOAD):
            chunks.append(out[i:i + MAX_CONTROL_PAYLOAD])
        return chunks

    async def _send_tls_chunks(self, chunks: list[bytes]):
        """Send TLS output as P_CONTROL_V1 packets."""
        for chunk in chunks:
            pid = self._reliable.next_send_id()
            await self._send_control(P_CONTROL_V1, chunk, msg_packet_id=pid)

    async def _feed_tls_input(self, parsed: dict):
        """Feed control packet payload into TLS input BIO."""
        if parsed["msg_packet_id"] is not None:
            payloads = self._reliable.data_received(parsed["msg_packet_id"], parsed["payload"])
            for p in payloads:
                if p:
                    self._ossl_conn.bio_write(p)
        # Send ACK
        await self._send_ack()

    # -- Main connect flow --

    async def connect(self) -> dict:
        """Establish the OpenVPN tunnel. Returns {"ok": True} or {"ok": False, "error": "..."}."""
        try:
            return await asyncio.wait_for(self._connect_inner(), timeout=30)
        except asyncio.TimeoutError:
            await self._cleanup()
            return {"ok": False, "error": "Timeout 30s — VPN-tilkobling feilet"}
        except Exception as e:
            logger.exception("Tunnel connect failed")
            await self._cleanup()
            return {"ok": False, "error": str(e)}

    async def _connect_inner(self) -> dict:
        # 1. Parse tls-auth key
        hmac_send, hmac_recv = parse_tls_auth_key(self.tls_auth_key_hex)

        # 2. TCP connect
        logger.info("Connecting to %s:443 ...", self.gateway)
        self._reader, self._writer = await asyncio.open_connection(self.gateway, 443)
        logger.info("TCP connected to %s:443", self.gateway)

        # 3. Generate session ID
        self._session_id = os.urandom(SID_SIZE)
        self._reliable = ReliableLayer()
        self._control = ControlChannel(self._session_id, hmac_send, hmac_recv)

        # 4. Send HARD_RESET_CLIENT
        pid = self._reliable.next_send_id()
        await self._send_control(P_CONTROL_HARD_RESET_CLIENT_V2, b"", msg_packet_id=pid)
        logger.debug("Sent HARD_RESET_CLIENT")

        # 5. Receive HARD_RESET_SERVER
        resp = await self._recv_control()
        if resp["opcode"] != P_CONTROL_HARD_RESET_SERVER_V2:
            return {"ok": False, "error": f"Uventet opcode: {resp['opcode']} (forventet HARD_RESET_SERVER)"}
        self._peer_sid = resp["session_id"]
        if resp["msg_packet_id"] is not None:
            self._reliable.data_received(resp["msg_packet_id"], resp["payload"])
        await self._send_ack()
        logger.debug("Received HARD_RESET_SERVER, peer_sid=%s", self._peer_sid.hex())

        # 6. TLS handshake via pyOpenSSL memory BIOs (needed for EKM)
        _ctx = _ossl.Context(_ossl.TLS_CLIENT_METHOD)
        _ctx.set_min_proto_version(_ossl.TLS1_2_VERSION)
        # Load CA cert
        _x509 = _ocrypto.load_certificate(_ocrypto.FILETYPE_PEM, self.ca_cert.encode())
        _store = _ctx.get_cert_store()
        _store.add_cert(_x509)
        _ctx.set_verify(_ossl.VERIFY_PEER, lambda *a: True)

        self._ossl_conn = _ossl.Connection(_ctx, None)
        self._ossl_conn.set_connect_state()
        self._ossl_conn.set_tlsext_host_name(self.gateway.encode())

        logger.debug("Starting TLS handshake")
        handshake_done = False
        while not handshake_done:
            try:
                self._ossl_conn.do_handshake()
                handshake_done = True
            except _ossl.WantReadError:
                # Read pending TLS output from pyOpenSSL
                chunks = self._flush_tls_output()
                if chunks:
                    await self._send_tls_chunks(chunks)
                # Read server response
                parsed = await self._recv_control()
                await self._feed_tls_input(parsed)

        # Flush final TLS output (e.g., Finished message)
        chunks = self._flush_tls_output()
        if chunks:
            await self._send_tls_chunks(chunks)
        logger.info("TLS handshake completed")

        # 7. Send Key Method 2
        pre_master = os.urandom(48)
        random1 = os.urandom(32)
        random2 = os.urandom(32)

        options_str = (
            "V4,dev-type tun,link-mtu 1500,tun-mtu 1551,"
            "proto TCPv4_CLIENT,keydir 1,cipher AES-256-GCM,auth [null-digest],"
            "keysize 256,tls-auth,key-method 2,tls-client"
        )
        peer_info_str = (
            "IV_VER=3.0.0\n"
            "IV_PLAT=linux\n"
            "IV_PROTO=1\n"
        )

        km2 = build_key_method_2(
            pre_master, random1, random2,
            options_str, "AzureAD", self.access_token, peer_info_str)

        self._ossl_conn.write(km2)
        chunks = self._flush_tls_output()
        await self._send_tls_chunks(chunks)
        logger.info("Sent Key Method 2 (%d bytes, token=%d bytes)", len(km2), len(self.access_token))

        # 8. Receive server's Key Method 2
        server_km2_data = b""
        while True:
            try:
                server_km2_data += self._ossl_conn.read(8192)
                break
            except _ossl.WantReadError:
                parsed = await self._recv_control()
                await self._feed_tls_input(parsed)

        server_km2 = parse_key_method_2_server(server_km2_data)
        logger.info("Received server Key Method 2, options: %s", server_km2["options"])
        # 9. Send PUSH_REQUEST
        self._ossl_conn.write(b"PUSH_REQUEST\x00")
        chunks = self._flush_tls_output()
        await self._send_tls_chunks(chunks)
        logger.debug("Sent PUSH_REQUEST")

        # 10. Receive PUSH_REPLY (server may send other messages first)
        push_data = b""
        for _attempt in range(60):
            try:
                chunk = self._ossl_conn.read(16384)
                logger.info("TLS read %d bytes: %s", len(chunk), chunk[:200])
                push_data += chunk
                if b"\x00" in push_data:
                    break
            except _ossl.WantReadError:
                try:
                    raw = await asyncio.wait_for(self._tcp_recv(), timeout=1.0)
                    opcode = (raw[0] >> P_OPCODE_SHIFT) & 0x1F
                    logger.info("RAW RECV after PUSH_REQUEST: opcode=%d len=%d hex=%s",
                                opcode, len(raw), raw[:40].hex())
                    if opcode in (P_DATA_V1, P_DATA_V2):
                        # Server might send data channel packets already
                        continue
                    parsed = self._control.parse_packet(raw)
                    if parsed:
                        self._reliable.ack_received(parsed["ack_ids"])
                        if parsed["msg_packet_id"] is not None:
                            payloads = self._reliable.data_received(
                                parsed["msg_packet_id"], parsed["payload"])
                            for p in payloads:
                                if p:
                                    self._ossl_conn.bio_write(p)
                        await self._send_ack()
                except asyncio.TimeoutError:
                    logger.debug("No data from server (attempt %d)", _attempt)

        push_str = push_data.split(b"\x00")[0].decode("utf-8", errors="replace")
        logger.info("PUSH_REPLY (full): %s", push_str)
        push = parse_push_reply(push_str)

        if not push["ifconfig_local"]:
            return {"ok": False, "error": "Server sendte ikke ifconfig i PUSH_REPLY"}

        # 11. Derive data channel keys — try EKM first, fall back to PRF
        logger.info("Deriving keys via TLS EKM (export_keying_material)")
        ekm_material = self._ossl_conn.export_keying_material(
            b"EXPORTER-OpenVPN-datakeys", 256, b"")
        # Layout: keys[0](128 bytes) + keys[1](128 bytes)
        # Each key: cipher(64) + hmac(64)
        # Direction 1 (client): encrypt=keys[1], decrypt=keys[0]
        keys = {
            "client_cipher_key": ekm_material[128:160],
            "server_cipher_key": ekm_material[0:32],
            "client_implicit_iv": ekm_material[192:204],
            "server_implicit_iv": ekm_material[64:76],
        }

        # Also compute PRF keys for comparison/debugging
        prf_keys = derive_keys(
            pre_master, random1, server_km2["random1"],
            random2, server_km2["random2"],
            self._session_id, self._peer_sid)

        logger.info("Data channel: peer_id=%d, use_ekm=%s, cipher=%s",
                    push["peer_id"], push["use_ekm"], push["cipher"])
        logger.debug("Keys: enc=%s dec=%s iv_enc=%s iv_dec=%s",
                     keys["client_cipher_key"][:8].hex(),
                     keys["server_cipher_key"][:8].hex(),
                     keys["client_implicit_iv"].hex(),
                     keys["server_implicit_iv"].hex())

        self._data_channel = DataChannel(
            key_encrypt=keys["client_cipher_key"],
            key_decrypt=keys["server_cipher_key"],
            iv_encrypt=keys["client_implicit_iv"],
            iv_decrypt=keys["server_implicit_iv"],
            peer_id=push["peer_id"],
            key_id=self._key_id,
        )

        # 12. Create and configure TUN device
        self._tun = TunDevice("tun0")
        try:
            await self._tun.open()
        except PermissionError as e:
            return {"ok": False, "error": str(e) or "Trenger root-tilgang for TUN-enhet"}
        except OSError as e:
            return {"ok": False, "error": f"Kunne ikke åpne /dev/net/tun: {e}"}

        await self._tun.configure(push["ifconfig_local"], push["ifconfig_remote"])
        logger.info("TUN configured: %s / %s", push["ifconfig_local"], push["ifconfig_remote"])

        # Add routes from PUSH_REPLY
        for network, netmask in push["routes"]:
            await self._tun.add_route(network, netmask)

        # Add routes from config
        for route in self.routes:
            route = route.strip()
            if "/" in route:
                parts = route.split("/")
                await self._tun.add_route(parts[0], parts[1])

        # Configure DNS
        for dns in (push["dns_servers"] or self.dns_servers):
            try:
                proc = await asyncio.create_subprocess_exec(
                    "sudo", "resolvectl", "dns", self._tun.name, dns,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                await asyncio.wait_for(proc.communicate(), 5)
            except Exception as e:
                logger.debug("Failed to set DNS %s: %s", dns, e)

        # 13. Start relay tasks
        self._running = True
        self._last_recv_time = time.monotonic()
        self._tasks = [
            asyncio.create_task(self._tcp_reader_loop(), name="tcp_reader"),
            asyncio.create_task(self._tun_reader_loop(), name="tun_reader"),
            asyncio.create_task(self._keepalive_loop(push["ping"]), name="keepalive"),
            asyncio.create_task(self._retransmit_loop(), name="retransmit"),
        ]

        logger.info("Azure VPN tunnel established via pure Python tunnel")
        return {"ok": True}

    # -- Relay tasks --

    async def _tcp_reader_loop(self):
        """Read from TCP socket, dispatch control or data packets."""
        data_recv_count = 0
        try:
            while self._running:
                data = await self._tcp_recv()
                self._last_recv_time = time.monotonic()
                opcode = (data[0] >> P_OPCODE_SHIFT) & 0x1F

                if opcode in (P_DATA_V1, P_DATA_V2):
                    data_recv_count += 1
                    plaintext = self._data_channel.decrypt(data)
                    if plaintext is None:
                        continue
                    if plaintext == PING_PAYLOAD:
                        continue
                    try:
                        os.write(self._tun.fileno(), plaintext)
                    except OSError as e:
                        logger.debug("TUN write error: %s", e)
                elif opcode in (P_CONTROL_V1, P_ACK_V1):
                    parsed = self._control.parse_packet(data)
                    if parsed:
                        self._reliable.ack_received(parsed["ack_ids"])
                        if parsed["msg_packet_id"] is not None:
                            payloads = self._reliable.data_received(
                                parsed["msg_packet_id"], parsed["payload"])
                            for p in payloads:
                                if p:
                                    self._ossl_conn.bio_write(p)
                        await self._send_ack()
        except (asyncio.IncompleteReadError, ConnectionResetError, OSError):
            logger.info("TCP connection closed")
        except asyncio.CancelledError:
            return
        finally:
            if self._running:
                self._running = False
                logger.info("TCP reader exiting, triggering disconnect")

    async def _tun_reader_loop(self):
        """Read from TUN device, encrypt and send to TCP."""
        loop = asyncio.get_event_loop()
        try:
            while self._running:
                try:
                    data = await asyncio.wait_for(
                        loop.run_in_executor(None, os.read, self._tun.fileno(), 2000),
                        timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                if data and self._data_channel:
                    encrypted = self._data_channel.encrypt(data)
                    await self._tcp_send(encrypted)
        except asyncio.CancelledError:
            return
        except OSError:
            logger.debug("TUN read error, likely closed")

    async def _keepalive_loop(self, interval: int = 10):
        """Send keepalive pings and detect dead connections."""
        try:
            while self._running:
                await asyncio.sleep(interval)
                if not self._running:
                    break
                # Send ping
                if self._data_channel:
                    ping_pkt = self._data_channel.encrypt(PING_PAYLOAD)
                    await self._tcp_send(ping_pkt)
                # Check for dead connection
                if time.monotonic() - self._last_recv_time > 60:
                    logger.warning("No data from server for 60s, disconnecting")
                    self._running = False
        except asyncio.CancelledError:
            return

    async def _retransmit_loop(self):
        """Re-send unacked control packets."""
        try:
            while self._running:
                await asyncio.sleep(1)
                for raw_pkt in self._reliable.get_retransmits():
                    await self._tcp_send(raw_pkt)
        except asyncio.CancelledError:
            return

    # -- Disconnect --

    async def disconnect(self) -> dict:
        """Tear down the tunnel."""
        self._running = False

        for task in self._tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
        self._tasks.clear()

        await self._cleanup()
        logger.info("Tunnel disconnected")
        return {"ok": True}

    async def _cleanup(self):
        if self._tun:
            self._tun.close()
            # Also delete the interface explicitly
            try:
                proc = await asyncio.create_subprocess_exec(
                    "sudo", "ip", "link", "delete", self._tun.name,
                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
                await asyncio.wait_for(proc.communicate(), 5)
            except Exception:
                pass
            self._tun = None

        if self._writer:
            try:
                self._writer.close()
                await self._writer.wait_closed()
            except Exception:
                pass
            self._writer = None
            self._reader = None
