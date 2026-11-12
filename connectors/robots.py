"""Evaluación de robots.txt según RFC 9309 (gana la regla más larga).

`urllib.robotparser` aplica "primera regla que casa", lo que interpreta mal
ficheros reales como el del visor del Cantábrico (Disallow: /wp-admin/ seguido
de Allow: /wp-admin/admin-ajax.php). Por eso hay implementación propia.
"""
from __future__ import annotations

import re


def _parse(robots_txt: str) -> list[tuple[list[str], list[tuple[str, str]]]]:
    groups: list[tuple[list[str], list[tuple[str, str]]]] = []
    agents: list[str] = []
    rules: list[tuple[str, str]] = []
    in_rules = False
    for line in robots_txt.splitlines():
        line = line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (part.strip() for part in line.split(":", 1))
        key = key.lower()
        if key == "user-agent":
            if in_rules:
                groups.append((agents, rules))
                agents, rules, in_rules = [], [], False
            agents.append(value.lower())
        elif key in ("allow", "disallow"):
            if agents:
                in_rules = True
                rules.append((key, value))
    if agents:
        groups.append((agents, rules))
    return groups


def _pattern_to_regex(pattern: str) -> re.Pattern[str]:
    anchored = pattern.endswith("$")
    if anchored:
        pattern = pattern[:-1]
    body = ".*".join(re.escape(part) for part in pattern.split("*"))
    return re.compile("^" + body + ("$" if anchored else ""))


def is_allowed(robots_txt: str, user_agent: str, path: str) -> bool:
    """¿Puede `user_agent` pedir `path` (ruta + query) según `robots_txt`?"""
    ua = user_agent.lower()
    groups = _parse(robots_txt)
    specific = [rules for agents, rules in groups if any(a != "*" and a in ua for a in agents)]
    chosen = specific or [rules for agents, rules in groups if "*" in agents]
    best_len = -1
    allowed = True
    for rules in chosen:
        for kind, pattern in rules:
            if not pattern:
                continue  # "Disallow:" vacío no restringe nada
            if _pattern_to_regex(pattern).match(path):
                length = len(pattern)
                if length > best_len or (length == best_len and kind == "allow"):
                    best_len = length
                    allowed = kind == "allow"
    return allowed
