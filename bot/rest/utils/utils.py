def try_get(dictionary, key, lower=False, typer=lambda x: x, default=None):
    value = typer(dictionary[key] if key in dictionary else default)
    return value.lower() if lower and isinstance(value, str) else value
