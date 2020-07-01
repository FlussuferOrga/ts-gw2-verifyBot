def try_get(dictionary, key, lower=False, typer=lambda x: x, default=None):
    v = typer(dictionary[key] if key in dictionary else default)
    return v.lower() if lower and isinstance(v, str) else v
