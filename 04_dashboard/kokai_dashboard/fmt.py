"""Formato chileno: miles con punto, decimales con coma."""


def num(x, d: int = 0) -> str:
    return f"{x:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def clp(x) -> str:
    return ("-" if x < 0 else "") + "$" + num(abs(x))


def clp_md(x) -> str:
    """clp() para texto markdown (st.caption/markdown): escapa el $ para que no se lea como fórmula."""
    return clp(x).replace("$", "\\$")


def pct(x, d: int = 1) -> str:
    return num(x * 100, d) + " %"


def pts(x, d: int = 2) -> str:
    return ("+" if x > 0 else "") + num(x, d) + " pts"
