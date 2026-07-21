"""Radiografia del dataset storico, per capire di quali stagioni ci si puo' fidare.

    python diagnosi_storico.py

Serve a rispondere a una domanda precisa: le voci anomale sono partite NON
GIOCATE (da scartare) o partite giocate salvate male (da tenere)? Il test e' la
distribuzione nel calendario: le partite non giocate si ammassano in fondo alla
stagione, quelle vere sono sparse su tutte le giornate.
"""

import re
from collections import Counter

from fantaportieri.config import STAGIONI_STORICHE
from fantaportieri.scrapers.rete import scarica_json
from fantaportieri.scrapers.storico_openfootball import URL


def _giornata(partita: dict) -> int:
    m = re.search(r"(\d+)", partita.get("round", ""))
    return int(m.group(1)) if m else 0


def _riassumi_giornate(giornate: list[int]) -> str:
    if not giornate:
        return "-"
    return (
        f"min={min(giornate)} max={max(giornate)} "
        f"mediana={sorted(giornate)[len(giornate) // 2]} "
        f"distinte={len(set(giornate))}"
    )


def diagnosi(stagione: str) -> None:
    dati = scarica_json(URL.format(stagione=stagione))
    partite = dati["matches"]

    dizionario: list[tuple[int, int]] = []
    lista: list[tuple[int, int]] = []
    lista_giornate: list[int] = []
    senza: list[int] = []

    for p in partite:
        s = p.get("score")
        if isinstance(s, dict) and isinstance(s.get("ft"), list):
            dizionario.append(tuple(s["ft"]))
        elif isinstance(s, list) and len(s) == 2:
            lista.append(tuple(s))
            lista_giornate.append(_giornata(p))
        else:
            senza.append(_giornata(p))

    print(f"== {stagione} ==  {len(partite)} partite in calendario")

    if dizionario:
        gol = sum(a + b for a, b in dizionario) / len(dizionario)
        zeri = sum(1 for r in dizionario if r == (0, 0))
        print(
            f"   forma dizionario: {len(dizionario):3d} partite | {gol:.2f} gol/partita "
            f"| 0-0 = {zeri / len(dizionario):.1%}"
        )

    if lista:
        distinti = Counter(lista)
        print(f"   forma lista:      {len(lista):3d} partite | risultati: {dict(distinti)}")
        print(f"                     giornate: {_riassumi_giornate(lista_giornate)}")
        sparse = len(set(lista_giornate)) > 20
        print(
            "                     -> sparse su tutta la stagione: sono PARTITE VERE"
            if sparse
            else "                     -> concentrate a fine stagione: NON GIOCATE"
        )

    if senza:
        print(f"   senza risultato:  {len(senza):3d} partite | giornate: {_riassumi_giornate(senza)}")

    # Verifica d'insieme: tenendo tutto, il campionato torna verosimile?
    tutte = dizionario + lista
    if tutte:
        gol_tot = sum(a + b for a, b in tutte) / len(tutte)
        zeri_tot = sum(1 for r in tutte if r == (0, 0)) / len(tutte)
        print(f"   TENENDO TUTTO:    {len(tutte):3d} partite | {gol_tot:.2f} gol/partita | 0-0 = {zeri_tot:.1%}")
    print()


if __name__ == "__main__":
    print("Riferimento Serie A reale: ~2.5-3.0 gol/partita, 0-0 nel 6-10% delle partite.\n")
    for s in STAGIONI_STORICHE:
        diagnosi(s)
