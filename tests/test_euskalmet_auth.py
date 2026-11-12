"""JWT de Euskalmet según la guía oficial ("How to use Meteo Rest Services")."""
from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from connectors.euskalmet_auth import AUDIENCE, PRODUCTION, build_jwt

NOW = datetime(2026, 11, 12, 13, 0, tzinfo=timezone.utc)


@pytest.fixture(scope="module")
def keys():
    k = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    priv = k.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
    pub = k.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    return priv, pub


def test_jwt_con_los_claims_fijos_de_la_guia(keys):
    priv, pub = keys
    token = build_jwt(priv, email="yo@ejemplo.es", issuer="Aguas Arriba", now=NOW, minutes=60)
    assert jwt.get_unverified_header(token)["alg"] == "RS256"
    c = jwt.decode(token, pub, algorithms=["RS256"], audience="met01.apikey", options={"verify_exp": False})
    assert c == {"aud": "met01.apikey", "iss": "Aguas Arriba", "version": "1.0.0", "email": "yo@ejemplo.es",
                 "iat": int(NOW.timestamp()), "exp": int(NOW.timestamp()) + 3600}
    assert AUDIENCE == "met01.apikey" and PRODUCTION == "https://api.euskadi.eus"


def test_clave_con_saltos_escapados_como_en_los_secretos(keys):
    priv, pub = keys
    token = build_jwt(priv.replace("\n", "\\n"), email="yo@ejemplo.es", now=NOW)
    assert jwt.decode(token, pub, algorithms=["RS256"], audience="met01.apikey", options={"verify_exp": False})


@pytest.mark.parametrize("email", ["", "no-es-un-email"])
def test_sin_email_valido_falla_en_claro(keys, email):
    with pytest.raises(ValueError):
        build_jwt(keys[0], email=email, now=NOW)


def test_script_local_imprime_solo_el_token(keys, tmp_path):
    pem = tmp_path / "priv.pem"
    pem.write_text(keys[0])
    out = subprocess.run([sys.executable, "scripts/euskalmet_jwt.py", "--key", str(pem), "--email", "yo@ejemplo.es", "--days", "7"],
                         capture_output=True, text=True, cwd=Path(__file__).resolve().parent.parent)
    assert out.returncode == 0, out.stderr
    token = out.stdout.strip()
    c = jwt.decode(token, keys[1], algorithms=["RS256"], audience="met01.apikey")
    assert c["exp"] - c["iat"] == 7 * 86400 and "BEGIN" not in out.stdout
