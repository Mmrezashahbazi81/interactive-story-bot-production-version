def btn(text: str, callback_data: str) -> dict:
    return {
        "text": text,
        "callback_data": callback_data,
    }


def ikb(rows: list[list[dict]]) -> dict:
    return {
        "inline_keyboard": rows
    }