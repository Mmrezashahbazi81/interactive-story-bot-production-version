def pack_callback(*parts: str) -> str:
    return ":".join(str(p).strip() for p in parts if str(p).strip())


def unpack_callback(data: str | None) -> list[str]:
    if not data:
        return []
    return data.split(":")