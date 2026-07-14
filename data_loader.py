import pandas as pd
import glob
import os
import re
import hashlib
from manual_tx_store import load_manual_store

def clean_ticker(base_currency_name):
    """
    Vysvětlení pro tebe (Educational explanation):
    Tato funkce vezme text jako "NVDA (NVIDIA Corp)" a vrátí pouze "NVDA".
    V Pythonu pracujeme s textem (tzv. řetězce neboli 'strings').
    Metoda `.split(" (")` rozdělí text na dvě části v místě, kde začíná závorka.
    Pokud se rozdělení podaří, vezmeme první část (index 0).
    """
    if not isinstance(base_currency_name, str):
        return base_currency_name
    
    # Rozdělíme řetězec podle " (" a vezmeme první část
    parts = base_currency_name.split(" (")
    ticker = parts[0].strip()
    
    # Občas může ticker obsahovat speciální znaky, ale yfinance potřebuje čistý ticker.
    return ticker

def _gen_tx_id(row):
    """
    Generuje deterministické ID transakce jako zkrácený SHA1 hash.

    Vysvětlení pro tebe (Educational explanation):
    SHA1 je hashovací funkce – dostane text a vrátí vždy stejný "otisk".
    Díky tomu máme pro každou transakci stabilní ID, které se nemění
    ani po restartu aplikace. Používáme ho pro sledování editací a smazání.
    """
    try:
        base_amt = float(row['Base amount'])
    except (ValueError, TypeError):
        base_amt = 0.0
    key = (
        f"{str(row['Date'])}"
        f"|{str(row.get('Broker_File', ''))}"
        f"|{str(row.get('Ticker', ''))}"
        f"|{str(row.get('Way', ''))}"
        f"|{base_amt:.8f}"
    )
    return hashlib.sha1(key.encode('utf-8')).hexdigest()[:16]


def load_transactions(directory_path="."):
    """
    Načte všechny CSV soubory s exporty z Delty v zadaném adresáři.
    """
    # Vyhledáme všechny soubory začínající na "delta_" a končící na ".csv"
    csv_files = glob.glob(os.path.join(directory_path, "delta_*.csv"))
    
    all_dfs = []
    
    for file_path in csv_files:
        # Zjistíme jméno brokera z názvu souboru (např. delta_FIO_26062026.csv -> FIO)
        filename = os.path.basename(file_path)
        parts = filename.split("_")
        if len(parts) >= 2:
            broker_name = parts[1]
        else:
            broker_name = "Unknown"
            
        print(f"Načítám transakce pro brokera: {broker_name} ze souboru {filename}")
        
        # Načteme CSV pomocí knihovny pandas
        # Pandas načte tabulku jako objekt DataFrame (něco jako tabulka v Excelu)
        df = pd.read_csv(file_path)
        
        # Přidáme sloupec s názvem brokera
        df['Broker_File'] = broker_name
        all_dfs.append(df)
        
    if not all_dfs:
        raise FileNotFoundError("Nebyly nalezeny žádné CSV soubory začínající na 'delta_'.")
        
    # Spojíme všechny tabulky do jedné velké tabulky
    merged_df = pd.concat(all_dfs, ignore_index=True)
    
    # Převedeme sloupec s datem na skutečný datumový typ (Datetime) a vynutíme UTC
    merged_df['Date'] = pd.to_datetime(merged_df['Date'], utc=True)
    
    # Vyčistíme tickery
    merged_df['Ticker'] = merged_df['Base currency (name)'].apply(clean_ticker)
    
    # Seřadíme transakce chronologicky (od nejstarší po nejnovější)
    # To je naprosto klíčové pro správný výpočet průměrné nákupní ceny!
    merged_df = merged_df.sort_values(by='Date').reset_index(drop=True)

    # --- Přiřadíme stabilní unikátní ID každé transakci ---
    # Viz funkce _gen_tx_id výše. ID je potřeba pro editaci a smazání.
    merged_df['tx_id'] = merged_df.apply(_gen_tx_id, axis=1)
    # Příznak: byla transakce ručně upravena? (přeskočí split-korekci)
    merged_df['_manually_edited'] = False

    # --- Aplikujeme manuální změny z manual_transactions.json ---
    store = load_manual_store()

    # 1. Editace CSV transakcí: přepíšeme hodnoty upravených řádků
    for tx_id_key, changes in store.get("edited", {}).items():
        mask = merged_df['tx_id'] == tx_id_key
        if mask.any():
            for col, val in changes.items():
                if col in merged_df.columns:
                    if col == 'Date':
                        merged_df.loc[mask, col] = pd.to_datetime(val, utc=True)
                    else:
                        merged_df.loc[mask, col] = val
            # Označíme: split-korekce se na tuto transakci nevztahuje
            merged_df.loc[mask, '_manually_edited'] = True

    # 2. Smazání: odfiltrujeme transakce označené jako smazané
    deleted_ids = store.get("deleted_ids", [])
    if deleted_ids:
        merged_df = merged_df[~merged_df['tx_id'].isin(deleted_ids)].copy()

    # 3. Přidání: přidáme manuálně zadané transakce
    added = store.get("added", [])
    if added:
        added_df = pd.DataFrame(added)
        added_df['Date'] = pd.to_datetime(added_df['Date'], utc=True)
        # Doplníme chybějící sloupce prázdnými hodnotami
        for col in merged_df.columns:
            if col not in added_df.columns:
                added_df[col] = pd.NA
        added_df = added_df.reindex(columns=merged_df.columns)
        merged_df = pd.concat([merged_df, added_df], ignore_index=True)
        # Znovu seřadíme – nové transakce mohou mít libovolné datum
        merged_df = merged_df.sort_values(by='Date').reset_index(drop=True)

    return merged_df

def calculate_holdings(transactions_df):
    """
    Vypočítá aktuální stav portfolia (holdings) a průměrnou nákupní cenu (WACP).
    
    Metoda WACP (Weighted Average Cost Price):
    - Při NÁKUPU (BUY) se přičte množství a celková nákupní cena.
      Nová průměrná cena = celková hodnota nákupů / celkové množství.
    - Při PRODEJI (SELL) se odečte množství. Průměrná nákupní cena zůstává stejná.
    """
    # Slovník pro uchování stavu jednotlivých akcií u jednotlivých brokerů
    # Klíčem bude dvojice (Broker, Ticker)
    holdings = {}
    
    for idx, row in transactions_df.iterrows():
        broker = row['Broker_File']
        ticker = row['Ticker']
        way = row['Way']  # "BUY" nebo "SELL"
        qty = float(row['Base amount'])
        total_val = float(row['Quote amount'])
        currency = row['Quote currency']
        
        key = (broker, ticker)
        
        if key not in holdings:
            holdings[key] = {
                'broker': broker,
                'ticker': ticker,
                'quantity': 0.0,
                'total_cost': 0.0,
                'avg_price': 0.0,
                'currency': currency
            }
            
        stock = holdings[key]
        
        if way == 'BUY':
            # Přičteme množství a hodnotu transakce
            stock['quantity'] += qty
            stock['total_cost'] += total_val
            if stock['quantity'] > 0:
                stock['avg_price'] = stock['total_cost'] / stock['quantity']
        elif way == 'SELL':
            # Odečteme množství
            # Průměrná cena za akcii (avg_price) zůstává stejná, ale celková hodnota pozice klesá
            if stock['quantity'] >= qty:
                stock['quantity'] -= qty
                stock['total_cost'] = stock['quantity'] * stock['avg_price']
            else:
                # Ošetření případu, kdy by šlo množství do mínusen (např. kvůli zaokrouhlení)
                stock['quantity'] = 0.0
                stock['total_cost'] = 0.0
                stock['avg_price'] = 0.0
                
    # Převedeme náš slovník zpět do přehledné tabulky (Pandas DataFrame)
    holdings_list = list(holdings.values())
    holdings_df = pd.DataFrame(holdings_list)
    
    # Odfiltrujeme akcie, které už uživatel kompletně prodal (množství je 0)
    # Použijeme malou toleranci (např. 0.0001) kvůli drobným nepřesnostem při ukládání floatů
    holdings_df = holdings_df[holdings_df['quantity'] > 0.0001].reset_index(drop=True)
    
    return holdings_df


def calculate_closed_positions_fifo(transactions_df):
    """
    Vypočítá uzavřené obchodní pozice metodou FIFO (First In, First Out).

    Metoda FIFO:
    - Akcie nakoupené jako první jsou prodány jako první.
    - Každý prodej (SELL) se chronologicky spáruje s nejstaršími dostupnými nákupy (BUY).
    - Výsledkem je seznam uzavřených obchodů s realizovaným ziskem/ztrátou.

    Vrací DataFrame s uzavřenými pozicemi, kde každý řádek odpovídá
    jednomu spárování (část nebo celý nákup uzavřený jedním prodejem).
    """
    # Pracovní slovník: pro každou dvojici (broker, ticker) uchováváme frontu nákupů.
    # Každý prvek fronty je slovník: {'date': ..., 'qty': ..., 'price_per_share': ..., 'currency': ...}
    buy_queues = {}

    closed_trades = []  # Sem budeme ukládat realizované obchody

    # Transakce jsou již seřazeny chronologicky (od nejstarší), viz load_transactions
    for _, row in transactions_df.iterrows():
        broker = row['Broker_File']
        ticker = row['Ticker']
        way = row['Way']
        qty = float(row['Base amount'])
        total_val = float(row['Quote amount'])
        currency = row['Quote currency']
        date = row['Date']

        key = (broker, ticker)

        if way == 'BUY':
            # Přidáme nákup do fronty (queue) pro danou dvojici broker+ticker
            if key not in buy_queues:
                buy_queues[key] = []
            price_per_share = total_val / qty if qty > 0 else 0.0
            buy_queues[key].append({
                'date': date,
                'qty': qty,
                'price_per_share': price_per_share,
                'currency': currency,
            })

        elif way == 'SELL':
            # Prodáváme – párujeme s nákupy metodou FIFO
            sell_price_per_share = total_val / qty if qty > 0 else 0.0
            remaining_sell_qty = qty  # Kolik ještě musíme spárovat

            queue = buy_queues.get(key, [])

            while remaining_sell_qty > 1e-8 and queue:
                buy = queue[0]  # Nejstarší nákup

                # Kolik akcií z tohoto nákupu použijeme pro tento prodej?
                matched_qty = min(remaining_sell_qty, buy['qty'])

                # Realizovaný zisk/ztráta pro spárované množství
                buy_cost = matched_qty * buy['price_per_share']
                sell_proceeds = matched_qty * sell_price_per_share
                realized_pnl = sell_proceeds - buy_cost
                realized_pnl_pct = (realized_pnl / buy_cost * 100) if buy_cost > 0 else 0.0

                closed_trades.append({
                    'Broker': broker,
                    'Akcie': ticker,
                    'Měna': buy['currency'],
                    'Datum nákupu': buy['date'],
                    'Nákupní cena (1 ks)': buy['price_per_share'],
                    'Datum prodeje': date,
                    'Prodejní cena (1 ks)': sell_price_per_share,
                    'Množství': matched_qty,
                    'Náklady nákupu': buy_cost,
                    'Výnos prodeje': sell_proceeds,
                    'Realizovaný zisk/ztráta': realized_pnl,
                    'Realizovaný zisk/ztráta (%)': realized_pnl_pct,
                    'Drženo dní': (date - buy['date']).days,
                })

                # Aktualizujeme zbývající množství v nákupní frontě
                buy['qty'] -= matched_qty
                remaining_sell_qty -= matched_qty

                # Pokud je nákup zcela vyčerpán, odebereme ho z fronty
                if buy['qty'] < 1e-8:
                    queue.pop(0)

            # Pokud zbyde nepárovaný prodej (short sell apod.), ignorujeme
            # (v praxi by fronta neměla být prázdná při správných datech)

    if not closed_trades:
        return pd.DataFrame()

    closed_df = pd.DataFrame(closed_trades)
    # Seřadíme uzavřené pozice od nejnovějšího prodeje
    closed_df = closed_df.sort_values(by='Datum prodeje', ascending=False).reset_index(drop=True)
    return closed_df

# Rychlý testovací kód, který se spustí pouze pokud tento soubor pustíš přímo
if __name__ == "__main__":
    print("--- Testovaci beh parseru ---")
    try:
        tx = load_transactions()
        print(f"Celkem nacteno transakci: {len(tx)}")
        
        # Upravíme transakce o splity akcií (lokální import kvůli zamezení cyklické závislosti)
        from yfinance_helper import adjust_transactions_for_splits
        tx = adjust_transactions_for_splits(tx)
        
        print("\nPrvnich 5 nactenych transakci po splitech:")
        print(tx[['Date', 'Broker_File', 'Way', 'Ticker', 'Base amount', 'Quote amount', 'Quote currency']].head())
        
        holdings = calculate_holdings(tx)
        print(f"\nCelkem aktualne drzenych pozic: {len(holdings)}")
        print("\nAktualni stav portfolia:")
        print(holdings)
    except Exception as e:
        print(f"Chyba pri testovani: {e}")
