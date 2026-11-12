"""JWT para la API de Euskalmet (Open Data Euskadi), según la guía oficial
https://opendata.euskadi.eus/api-euskalmet/-/how-to-use-meteo-rest-services/

Cabecera alg=RS256. Claims: aud="met01.apikey" (fijo), iss, exp, version="1.0.0" (fijo), iat y email del
dueño de la clave. Firma con la clave PRIVADA. Se envía como `Authorization: Bearer <jwt>` a
https://api.euskadi.eus (el sandbox de la documentación es https://api.sandbox.euskadi.eus).

La clave privada nunca se guarda en el repositorio: llega por variable de entorno (EUSKALMET_PRIVATE_KEY).
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt

AUDIENCE = "met01.apikey"
VERSION = "1.0.0"
PRODUCTION = "https://api.euskadi.eus"


def build_jwt(private_key_pem: str, email: str, issuer: str = "Aguas Arriba",
              now: Optional[datetime] = None, minutes: int = 60) -> str:
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email or ""):
        raise ValueError("Euskalmet: hace falta el email asociado a la clave (EUSKALMET_EMAIL)")
    key = private_key_pem.replace("\\n", "\n").strip()  # en secretos suele venir con los saltos escapados
    now = now or datetime.now(timezone.utc)
    iat = int(now.timestamp())
    claims = {"aud": AUDIENCE, "iss": issuer, "version": VERSION, "email": email,
              "iat": iat, "exp": iat + int(timedelta(minutes=minutes).total_seconds())}
    return jwt.encode(claims, key, algorithm="RS256")
