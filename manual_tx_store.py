"""
Správa manuálních změn transakcí (manual_tx_store.py).

Vysvětlení pro tebe (Educational explanation):
Tento modul je zodpovědný za ukládání veškerých ručních změn do souboru
`manual_transactions.json`. Funguje jako jednoduchá "databáze" pro tři typy změn:
  - added      -> seznam ručně přidaných transakcí
  - deleted_ids -> seznam tx_id transakcí, které mají být skryty
  - edited     -> slovník {tx_id: {pole: nová_hodnota}} pro upravené řádky

Původní CSV soubory (delta_FIO, delta_Revolut, delta_XTB) NIKDY neměníme.
"""

import json
import os

MANUAL_TX_FILE = "manual_transactions.json"


def load_manual_store():
    """
    Načte soubor s manuálními změnami transakcí.
    Pokud soubor ještě neexistuje (první spuštění), vrátí prázdnou strukturu.
    """
    if os.path.exists(MANUAL_TX_FILE):
        with open(MANUAL_TX_FILE, "r", encoding="utf-8") as f:
            store = json.load(f)
            if "ath_overrides" not in store:
                store["ath_overrides"] = {}
            return store
    return {"added": [], "deleted_ids": [], "edited": {}, "ath_overrides": {}}


def save_manual_store(store):
    """
    Uloží manuální změny do JSON souboru.
    `default=str` zajistí, že datetime objekty se serializují jako řetězce.
    """
    with open(MANUAL_TX_FILE, "w", encoding="utf-8") as f:
        json.dump(store, f, indent=4, ensure_ascii=False, default=str)


def add_manual_transaction(store, tx_row):
    """
    Přidá novou manuální transakci do store.
    tx_row je slovník se všemi potřebnými poli (viz app.py).
    """
    store["added"].append(tx_row)
    return store


def delete_transaction(store, tx_id):
    """
    Označí transakci jako smazanou.
    Funguje pro oba typy transakcí:
      - CSV transakce      -> přidá tx_id do deleted_ids
      - Manuálně přidané  -> přímo odebere ze seznamu added[]
    """
    store["added"] = [t for t in store["added"] if t.get("tx_id") != tx_id]
    if tx_id not in store["deleted_ids"]:
        store["deleted_ids"].append(tx_id)
    return store


def edit_transaction(store, tx_id, changes):
    """
    Uloží editaci existující transakce.
    Pro manuálně přidané transakce: přímo aktualizuje záznam v added[].
    Pro CSV transakce: ukládá změny do edited{}, aplikují se při načítání.
    """
    found_in_added = False
    for i, tx in enumerate(store["added"]):
        if tx.get("tx_id") == tx_id:
            store["added"][i].update(changes)
            found_in_added = True
            break

    if not found_in_added:
        store["edited"][tx_id] = changes

    return store


def set_ath_override(store, ticker, ath_value):
    """
    Nastaví ruční přepsání ATH (All-Time High) pro konkrétní ticker.
    """
    store.setdefault("ath_overrides", {})[ticker] = float(ath_value)
    return store


def remove_ath_override(store, ticker):
    """
    Odstraní ruční přepsání ATH.
    """
    if "ath_overrides" in store and ticker in store["ath_overrides"]:
        del store["ath_overrides"][ticker]
    return store
