from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

_servers: list[asyncio.Server] = []

async def _handle_connect(
    local_reader: asyncio.StreamReader,
    local_writer: asyncio.StreamWriter,
    upstream_host: str,
    upstream_port: int,
    username: str,
    password: str,
):
    up_writer = None
    target = "unknown"
    try:
        # 1. Читаем HTTP CONNECT запрос от Playwright
        request = b''
        while b'\r\n\r\n' not in request:
            # Увеличили таймауты для мобильных прокси
            chunk = await asyncio.wait_for(local_reader.read(4096), timeout=15)
            if not chunk: return
            request += chunk

        first_line = request.split(b'\r\n')[0].decode('latin-1')
        parts = first_line.split(' ')
        if len(parts) < 2 or parts[0].upper() != 'CONNECT':
            local_writer.write(b'HTTP/1.1 400 Bad Request\r\n\r\n')
            await local_writer.drain()
            return

        target = parts[1]
        target_host, target_port_str = target.split(':')
        target_port = int(target_port_str)

        # 2. Подключаемся к ASocks по TCP (Ждем до 30 секунд для мобилок)
        up_reader, up_writer = await asyncio.wait_for(
            asyncio.open_connection(upstream_host, upstream_port),
            timeout=30,
        )

        # 3. SOCKS5 приветствие
        up_writer.write(b'\x05\x01\x02')
        await up_writer.drain()

        greeting = await asyncio.wait_for(up_reader.readexactly(2), timeout=15)
        if greeting != b'\x05\x02':
            raise Exception("SOCKS5 proxy rejected username/password method")

        # 4. SOCKS5 авторизация
        u_b = username.encode('utf-8')
        p_b = password.encode('utf-8')
        auth_req = b'\x01' + bytes([len(u_b)]) + u_b + bytes([len(p_b)]) + p_b
        up_writer.write(auth_req)
            
        await up_writer.drain()
        auth_resp = await asyncio.wait_for(up_reader.readexactly(2), timeout=15)
        if auth_resp[1] != 0x00:
            raise Exception("SOCKS5 invalid username or password")

        # 5. SOCKS5 команда CONNECT к целевому сайту
        host_b = target_host.encode('utf-8')
        conn_req = b'\x05\x01\x00\x03' + bytes([len(host_b)]) + host_b + target_port.to_bytes(2, 'big')
        up_writer.write(conn_req)
        await up_writer.drain()

        # Ждем ответ от Яндекса через прокси до 30 секунд
        conn_resp = await asyncio.wait_for(up_reader.readexactly(4), timeout=30)
        if conn_resp[1] != 0x00:
            raise Exception(f"SOCKS5 target connection failed, code: {conn_resp[1]}")

        # Пропускаем остаток ответа привязки адреса
        atype = conn_resp[3]
        if atype == 1:
            await asyncio.wait_for(up_reader.readexactly(6), timeout=10)
        elif atype == 3:
            l = await asyncio.wait_for(up_reader.readexactly(1), timeout=10)
            await asyncio.wait_for(up_reader.readexactly(l[0] + 2), timeout=10)
        elif atype == 4:
            await asyncio.wait_for(up_reader.readexactly(18), timeout=10)

        # 6. Сообщаем Playwright, что туннель успешно установлен
        local_writer.write(b'HTTP/1.1 200 Connection Established\r\n\r\n')
        await local_writer.drain()

        # 7. Перегоняем зашифрованный трафик
        async def relay(src, dst):
            try:
                while True:
                    data = await src.read(65536)
                    if not data: break
                    dst.write(data)
                    await dst.drain()
            except Exception:
                pass

        t1 = asyncio.create_task(relay(local_reader, up_writer))
        t2 = asyncio.create_task(relay(up_reader, local_writer))
        done, pending = await asyncio.wait([t1, t2], return_when=asyncio.FIRST_COMPLETED)
        for t in pending:
            t.cancel()

    # Явный перехват таймаутов, чтобы не было пустых строк в логах
    except asyncio.TimeoutError:
        logger.warning(f"[fwd] Timeout error connecting to {target} (proxy is slow)")
    except asyncio.IncompleteReadError:
        logger.warning(f"[fwd] Proxy closed connection unexpectedly for {target}")
    except Exception as e:
        logger.warning(f"[fwd] SOCKS5 bridge error for {target}: {e}")
        try:
            local_writer.write(b'HTTP/1.1 502 Bad Gateway\r\n\r\n')
            await local_writer.drain()
        except Exception:
            pass
    finally:
        if up_writer:
            try: up_writer.close()
            except Exception: pass
        try: local_writer.close()
        except Exception: pass


async def start_forwarder(
    listen_port: int,
    upstream_host: str,
    upstream_port: int,
    username: str,
    password: str,
) -> asyncio.Server:
    async def on_connect(reader, writer):
        await _handle_connect(reader, writer, upstream_host, upstream_port, username, password)
    server = await asyncio.start_server(on_connect, '127.0.0.1', listen_port)
    return server

async def _self_test(port: int) -> bool:
    try:
        reader, writer = await asyncio.wait_for(asyncio.open_connection('127.0.0.1', port), timeout=5)
        # Тестируем подключением к Яндексу, чтобы SOCKS5 не выдал код ошибки 5
        writer.write(b'CONNECT ya.ru:443 HTTP/1.1\r\nHost: ya.ru:443\r\n\r\n')
        await writer.drain()
        resp = await asyncio.wait_for(reader.read(1024), timeout=15)
        writer.close()
        return len(resp) > 0
    except Exception:
        return False

async def start_all(proxies: list[dict]) -> list[asyncio.Server]:
    global _servers
    servers = []
    for p in proxies:
        srv = await start_forwarder(
            listen_port=p['local_port'],
            upstream_host=p['upstream_host'],
            upstream_port=p['upstream_port'],
            username=p['username'],
            password=p['password'],
        )
        servers.append(srv)
    _servers = servers
    logger.info(f"Local proxy forwarders (SOCKS5 Bridge): {len(servers)} started")
    return servers

async def stop_all():
    global _servers
    for srv in _servers:
        srv.close()
    for srv in _servers:
        await srv.wait_closed()
    _servers = []
