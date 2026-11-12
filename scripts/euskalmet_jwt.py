#!/usr/bin/env python3
"""Genera EN TU PC un token temporal de Euskalmet a partir de tu clave privada.

    pip install "PyJWT[crypto]"
    python scripts/euskalmet_jwt.py --key ruta/a/tu_clave_privada.pem --email tu@correo.es --days 7

Imprime solo el token (no la clave). Pégalo en el formulario seguro que te abre Claude, NUNCA en el chat.
La clave privada no sale de tu ordenador.
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from connectors.euskalmet_auth import build_jwt  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", required=True, help="fichero .pem con la clave PRIVADA de Euskalmet")
    ap.add_argument("--email", required=True, help="email con el que pediste la clave")
    ap.add_argument("--days", type=int, default=7, help="días de validez del token (por defecto 7)")
    args = ap.parse_args()
    print(build_jwt(Path(args.key).read_text(), email=args.email, minutes=args.days * 24 * 60))
    return 0


if __name__ == "__main__":
    sys.exit(main())
