"""
Local proxy forwarder for 3proxy with proactive auth.

3proxy doesn't send HTTP 407 challenge — it expects Proxy-Authorization
upfront. Chromium won't send credentials without a 407. This forwarder
listens locally (no auth) and injects the auth header when connecting
upstream.

Usage:
    forwarders = await start_forwarders(proxies, local_port_base=13100)
    # forwarders = [{"server": "http://127.0.0.1:13100"}, ...]
    ...
    await stop_forwarders()
"""

from __future__ import annotations

import asyncio
import base64
import logging

logger = logging.getLogger(__name__)

_servers: list[asyncio.Server] = []


def _make_auth_header(username: str, password: str) -> bytes:
    creds = base64.b64encode(f"{username}:{password}".encode()).decode()
    return f"Proxy-Authorization: Basic {creds}\r\n".encode()


async def _pipe(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
    try:
        while True:
            data = await reader.read(65536)
            if not data:
                break
            writer.write(data)
            await writer.drain()
    except (ConnectionResetError, BrokenPipeError, OSError):
        pass
    finally:
        try:
            writer.close()
        except Exception:
            pass


async def _handle_connect(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    upstream_host: str,
    upstream_port: int,
    auth_header: bytes,
):
    """Handle one client connection: read request, forward to upstream with auth."""
    try:
        raw = b""
        while not raw.endswith(b"\r\n\r\n"):
            chunk = await asyncio.wait_for(client_reader.read(4096), timeout=10)
            if not chunk:
                client_writer.close()
                return
            raw += chunk

        first_line_end = raw.index(b"\r\n")
        first_line = raw[:first_line_end]

        upstream_reader, upstream_writer = await asyncio.wait_for(
            asyncio.open_connection(upstream_host, upstream_port),
            timeout=10,
        )

        if first_line.upper().startswith(b"CONNECT"):
            upstream_request = first_line + b"\r\n" + auth_header + b"\r\n"
            upstream_writer.write(upstream_request)
            await upstream_writer.drain()

            response = b""
            while not response.endswith(b"\r\n\r\n"):
                chunk = await asyncio.wait_for(upstream_reader.read(4096), timeout=10)
                if not chunk:
                    break
                response += chunk

            client_writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
            await client_writer.drain()
        else:
            new_request = first_line + b"\r\n" + auth_header
            rest = raw[first_line_end + 2:]
            upstream_writer.write(new_request + rest)
            await upstream_writer.drain()

        await asyncio.gather(
            _pipe(client_reader, upstream_writer),
            _pipe(upstream_reader, client_writer),
        )

    except Exception:
        pass
    finally:
        try:
            client_writer.close()
        except Exception:
            pass


async def start_forwarders(
    proxies: list[dict],
    local_port_base: int = 8000,
) -> list[dict]:
    """
    Start local TCP forwarders for each upstream proxy.

    Args:
        proxies: list of {"server": "http://host:port", "username": "...", "password": "..."}
        local_port_base: first local port to bind

    Returns:
        list of {"server": "http://127.0.0.1:<local_port>"} for Playwright
    """
    global _servers
    local_proxies: list[dict] = []

    for i, proxy in enumerate(proxies):
        server_url = proxy["server"]
        host = server_url.split("://")[-1].split(":")[0]
        port = int(server_url.split(":")[-1])
        username = proxy.get("username", "")
        password = proxy.get("password", "")
        auth_header = _make_auth_header(username, password) if username else b""

        local_port = local_port_base + i

        def make_handler(h, p, ah):
            async def handler(r, w):
                await _handle_connect(r, w, h, p, ah)
            return handler

        try:
            server = await asyncio.start_server(
                make_handler(host, port, auth_header),
                "127.0.0.1",
                local_port,
            )
            _servers.append(server)
            local_proxies.append({"server": f"http://127.0.0.1:{local_port}"})
        except OSError as e:
            logger.warning(f"Cannot bind port {local_port}: {e}")
            local_proxies.append(proxy)

    logger.info(f"Started {len(_servers)} local proxy forwarders (ports {local_port_base}-{local_port_base + len(proxies) - 1})")
    return local_proxies


async def stop_forwarders():
    global _servers
    for s in _servers:
        s.close()
    count = len(_servers)
    _servers.clear()
    if count:
        logger.info(f"Stopped {count} proxy forwarders")
