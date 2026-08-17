"""Helpers HTTP compartilhados pelos scrapers — sessão com retry, timeout e user-agent de navegador."""
from __future__ import annotations

import logging
import time

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger("career_agent.scrapers")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

DEFAULT_TIMEOUT = 15


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT, "Accept-Language": "pt-BR,pt;q=0.9"})
    retry = Retry(total=2, backoff_factor=1.5, status_forcelist=[429, 500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def polite_sleep(seconds: float = 1.0) -> None:
    """Pausa curta entre requisições à mesma plataforma para não parecer um ataque."""
    time.sleep(seconds)


def safe_get(session: requests.Session, url: str, *, params: dict | None = None, headers: dict | None = None):
    """GET tolerante a falha: retorna a Response em sucesso, ou None (logando) em qualquer erro."""
    try:
        response = session.get(url, params=params, headers=headers, timeout=DEFAULT_TIMEOUT)
        if response.status_code != 200:
            logger.warning("GET %s -> HTTP %s", response.url, response.status_code)
            return None
        return response
    except requests.RequestException as exc:
        logger.warning("GET %s falhou: %s", url, exc)
        return None
