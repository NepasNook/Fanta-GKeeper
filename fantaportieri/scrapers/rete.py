"""Utilita' di rete condivise dagli scraper. Solo libreria standard."""

import json
import time
import urllib.error
import urllib.request

# Wikimedia rifiuta gli User-Agent generici da browser: ne vuole uno descrittivo.
USER_AGENT = (
    "Fanta-GKeeper/0.1 (fantasy football side project; "
    "+https://github.com/NepasNook/Fanta-GKeeper)"
)


class ErroreRete(Exception):
    pass


def scarica_json(url: str, tentativi: int = 3, pausa: float = 1.5) -> dict | list:
    """GET con retry su errori temporanei. Solleva ErroreRete se non ce la fa."""
    richiesta = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}
    )
    ultimo = ""
    for tentativo in range(1, tentativi + 1):
        try:
            with urllib.request.urlopen(richiesta, timeout=60) as risposta:
                return json.loads(risposta.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            ultimo = f"HTTP {e.code}"
            # 4xx diversi da 429 non migliorano riprovando.
            if e.code != 429 and 400 <= e.code < 500:
                break
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
            ultimo = str(e)
        if tentativo < tentativi:
            time.sleep(pausa * tentativo)

    raise ErroreRete(f"{url} -> {ultimo}")
