import ipaddress
import re
import socket
from urllib.parse import urlparse

BLOCKED_DB_TYPES = frozenset({"sqlite"})


def validate_db_type(db_type: str) -> str:
    normalized = (db_type or "").strip().lower()
    if normalized in BLOCKED_DB_TYPES:
        raise ValueError(f"Database type '{normalized}' is not allowed")
    return normalized


def reject_raw_connection_string(connection_string: str) -> None:
    if (connection_string or "").strip():
        raise ValueError("connection_string is not accepted; provide host, port, database, and credentials")


TABLE_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "metadata.google.internal",
    }
)


def validate_table_names(tables: list) -> list[str]:
    if not tables:
        raise ValueError("tables list is required")
    validated: list[str] = []
    for table in tables:
        name = str(table).strip()
        if not TABLE_NAME_PATTERN.match(name):
            raise ValueError(f"Invalid table name: {name}")
        validated.append(name)
    return validated


def validate_db_host(host: str) -> str:
    host = (host or "").strip()
    if not host:
        raise ValueError("host is required")
    if host.lower() in BLOCKED_HOSTS:
        raise ValueError("Connection to this host is not allowed")
    return host


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved:
        return True
    if ip == ipaddress.ip_address("169.254.169.254"):
        return True
    return False


def assert_safe_connection_target(host: str, connection_string: str = "") -> None:
    hosts: list[str] = []
    if host:
        hosts.append(host.strip())

    if connection_string:
        parsed = urlparse(connection_string)
        if parsed.hostname:
            hosts.append(parsed.hostname)

    if not hosts:
        return

    for target in hosts:
        lowered = target.lower()
        if lowered in BLOCKED_HOSTS:
            raise ValueError("Connection to this host is not allowed")
        try:
            addr = ipaddress.ip_address(target)
            if _is_blocked_ip(addr):
                raise ValueError("Connection to private or reserved addresses is not allowed")
            continue
        except ValueError:
            pass

        try:
            for info in socket.getaddrinfo(target, None):
                resolved = info[4][0]
                addr = ipaddress.ip_address(resolved)
                if _is_blocked_ip(addr):
                    raise ValueError("Connection to private or reserved addresses is not allowed")
        except socket.gaierror as exc:
            raise ValueError(f"Unable to resolve database host: {target}") from exc
