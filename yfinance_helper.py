import yfinance as yf
import pandas as pd
import json
import os
from datetime import datetime

CACHE_FILE = "ath_cache.json"

def load_ath_cache():
    """
    Načte keš (cache) s All-Time High cenami ze souboru JSON.
    Vysvětlení: Kešování používáme k tomu, abychom nemuseli při každém
    spuštění aplikace stahovat 15 let historie pro všech 72 akcií.
    Uložíme si je do souboru a příště je načteme bleskově z disku.
    """
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_ath_cache(cache):
    """
    Uloží keš do souboru JSON.
    """
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=4)

SPLITS_CACHE_FILE = "splits_cache.json"

def load_splits_cache():
    """
    Načte keš splitů ze souboru JSON.
    """
    if os.path.exists(SPLITS_CACHE_FILE):
        with open(SPLITS_CACHE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_splits_cache(cache):
    """
    Uloží keš splitů do souboru JSON.
    """
    with open(SPLITS_CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=4)

def get_splits_for_ticker(ticker, cache):
    """
    Získá historii splitů pro daný ticker z keše nebo ji stáhne z Yahoo Finance.
    Keš expiruje po 7 dnech pro zajištění aktuálnosti.
    """
    now = datetime.now()
    
    # Ověříme, zda máme ticker v keši a zda keš nevypršela
    if ticker in cache:
        entry = cache[ticker]
        # Podpora pro nový formát (s datem aktualizace)
        if isinstance(entry, dict) and "last_updated" in entry:
            try:
                last_updated = datetime.fromisoformat(entry["last_updated"])
                if (now - last_updated).days < 7:
                    return entry["splits"]
            except Exception:
                pass
        # Zpětná kompatibilita pro starý formát (seznam splitů přímo)
        elif isinstance(entry, list):
            return entry
            
    print(f"Stahuji historii splitů pro {ticker}...")
    try:
        ticker_obj = yf.Ticker(ticker)
        splits = ticker_obj.splits
        splits_list = []
        if not splits.empty:
            for date_idx, ratio in splits.items():
                splits_list.append({
                    "date": date_idx.isoformat(),
                    "ratio": float(ratio)
                })
        
        # Uložíme do keše v novém formátu
        cache[ticker] = {
            "splits": splits_list,
            "last_updated": now.isoformat()
        }
        return splits_list
    except Exception as e:
        print(f"Chyba při stahování splitů pro {ticker}: {e}")
        # Pokud stahování selhalo, ale máme starší keš (i expirovanou), použijeme ji jako zálohu
        if ticker in cache:
            entry = cache[ticker]
            if isinstance(entry, dict):
                return entry.get("splits", [])
            return entry
        # Pokud nemáme žádná data, neukládáme prázdný výsledek, abychom se příště pokusili znovu
        return []

def adjust_transactions_for_splits(transactions_df):
    """
    Vysvětlení pro tebe (Educational explanation):
    Tato funkce projde všechny transakce a pokud se po datu nákupu/prodeje
    odehrál nějaký split (rozdělení akcií), vynásobí množství (Base amount)
    tímto poměrem.
    Porovnání se provádí robustně pomocí objektů datetime převedených na UTC,
    což eliminuje chyby spojené s časovými pásmy.
    """
    df = transactions_df.copy()
    cache = load_splits_cache()
    
    tickers = df['Ticker'].unique()
    
    # Stáhneme/aktualizujeme splity pro všechny jedinečné akcie v portfoliu
    for ticker in tickers:
        get_splits_for_ticker(ticker, cache)
        
    save_splits_cache(cache)
    
    # Upravíme množství u jednotlivých transakcí
    adjusted_amounts = []
    multipliers = []
    
    for idx, row in df.iterrows():
        ticker = row['Ticker']
        qty = float(row['Base amount'])
        tx_date = row['Date']
        
        # Přeskočíme manuálně upravené transakce.
        # Uživatel zadal množství přímo -> double-adjustment by byl chybný.
        if '_manually_edited' in row and row['_manually_edited']:
            adjusted_amounts.append(qty)
            multipliers.append(1.0)
            continue

        # Převedeme datum transakce na timezone-aware UTC datetime
        if tx_date.tzinfo is None:
            tx_date_utc = tx_date.tz_localize('UTC')
        else:
            tx_date_utc = tx_date.tz_convert('UTC')
            
        splits_info = cache.get(ticker, {})
        splits = splits_info.get("splits", []) if isinstance(splits_info, dict) else splits_info
        
        multiplier = 1.0
        
        for split in splits:
            try:
                split_date = pd.to_datetime(split['date'])
                if split_date.tzinfo is None:
                    split_date_utc = split_date.tz_localize('UTC')
                else:
                    split_date_utc = split_date.tz_convert('UTC')
            except Exception:
                continue
                
                # Pokud se split stal až PO transakci, navýšíme/upravíme množství
            if split_date_utc > tx_date_utc:
                multiplier *= split['ratio']
                
        adjusted_amounts.append(qty * multiplier)
        multipliers.append(multiplier)
        
    df['Original amount'] = df['Base amount']
    df['Base amount'] = adjusted_amounts
    df['Split Multiplier'] = multipliers
    return df

def fetch_current_prices(tickers):
    """
    Stáhne aktuální ceny pro seznam tickerů najednou (hromadně/batch).
    To je mnohem rychlejší než stahovat každou akcii zvlášť.
    """
    if not tickers:
        return {}
    
    print(f"Stahuji aktuální ceny pro {len(tickers)} tickerů...")
    # yf.download stáhne data pro všechny tickery najednou
    # period="1d" nám dá data za poslední den
    # Přidáno threads=False pro zabránění Segmentation fault na Streamlit Cloud
    data = yf.download(tickers, period="1d", group_by="ticker", progress=False, threads=False)
    
    current_prices = {}
    
    for ticker in tickers:
        try:
            # V závislosti na tom, zda stahujeme jeden nebo více tickerů,
            # může mít výstup z pandas jinou strukturu.
            if len(tickers) == 1:
                ticker_data = data
            else:
                ticker_data = data[ticker]
                
            # Vezmeme poslední známou uzavírací cenu (Close)
            if not ticker_data.empty:
                last_price = ticker_data['Close'].dropna().iloc[-1]
                current_prices[ticker] = float(last_price)
        except Exception as e:
            print(f"Nepodařilo se získat cenu pro {ticker}: {e}")
            
    return current_prices

def get_ath_for_ticker(ticker, current_price, cache):
    """
    Vrátí All-Time High (ATH) pro danou akcii za posledních 15 let.
    Pokud existuje manuální override v manual_transactions.json, použije se ten.
    Pokud je akcie v keši a aktuální cena nepřekonala ATH, použije se hodnota z keše.
    Jinak se stáhne historie a keš se aktualizuje.
    """
    from manual_tx_store import load_manual_store
    store = load_manual_store()
    overrides = store.get("ath_overrides", {})
    if ticker in overrides:
        # Pokud máme manuální override, vždy použijeme ten a přeskočíme stahování historie/keš
        return float(overrides[ticker])

    # Pokud již máme ATH v keši
    if ticker in cache:
        cached_ath = cache[ticker]["ath"]
        # Pokud aktuální cena překonala staré ATH, aktualizujeme ho
        if current_price > cached_ath:
            cache[ticker]["ath"] = current_price
            cache[ticker]["date"] = datetime.now().strftime("%Y-%m-%d")
            return current_price
        return cached_ath
        
    # Pokud v keši není, stáhneme 15letou historii
    print(f"Keš neobsahuje {ticker}. Stahuji 15letou historii pro výpočet ATH...")
    try:
        ticker_obj = yf.Ticker(ticker)
        # Stáhneme historická denní data za 15 let (15y)
        hist = ticker_obj.history(period="15y")
        if not hist.empty:
            ath_value = float(hist['High'].max())
            # Zjistíme datum, kdy bylo ATH dosaženo
            ath_date_idx = hist['High'].idxmax()
            ath_date_str = ath_date_idx.strftime("%Y-%m-%d")
            
            # Uložíme do keše
            cache[ticker] = {
                "ath": ath_value,
                "date": ath_date_str
            }
            return ath_value
    except Exception as e:
        print(f"Chyba při stahování historie pro {ticker}: {e}")
        
    # Záložní možnost: pokud stahování selže, použijeme aktuální cenu jako ATH
    return current_price

def fetch_market_caps(tickers):
    """
    Stáhne tržní kapitalizaci (market cap) pro seznam tickerů.
    Vrací slovník {ticker: market_cap}, kde market_cap je číslo (int/float)
    nebo None, pokud se hodnotu nepodařilo získat.
    """
    if not tickers:
        return {}

    print(f"Stahuji tržní kapitalizaci pro {len(tickers)} tickerů...")
    market_caps = {}

    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).info
            market_caps[ticker] = info.get("marketCap", None)
        except Exception as e:
            print(f"Nepodařilo se získat market cap pro {ticker}: {e}")
            market_caps[ticker] = None

    return market_caps


def fetch_sectors(tickers):
    """
    Stáhne název sektoru pro seznam tickerů z Yahoo Finance.
    Vrací slovník {ticker: sector}, kde sector je řetězec (např. "Technology")
    nebo "Neznámý", pokud se hodnotu nepodařilo získat.

    Vysvětlení pro tebe (Educational explanation):
    Každá akcie na Yahoo Finance má přiřazený sektor (např. Technology, Healthcare,
    Financial Services...). Tuto informaci najdeme ve slovníku .info, kde je
    uložena pod klíčem "sector". Pokud ticker není akcie (ETF, fond), klíč nemusí
    existovat – proto použijeme .get() s výchozí hodnotou "Ostatní".
    """
    if not tickers:
        return {}

    print(f"Stahuji sektory pro {len(tickers)} tickerů...")
    sectors = {}

    for ticker in tickers:
        try:
            info = yf.Ticker(ticker).info
            sectors[ticker] = info.get("sector") or "Ostatní"
        except Exception as e:
            print(f"Nepodařilo se získat sektor pro {ticker}: {e}")
            sectors[ticker] = "Ostatní"

    return sectors


def update_portfolio_prices(holdings_df):

    """
    Obohatí tabulku držených pozic o aktuální cenu, celkovou aktuální hodnotu,
    ATH a rozdíl od ATH (v procentech).
    """
    tickers = list(holdings_df['ticker'].unique())
    current_prices = fetch_current_prices(tickers)
    
    # Načteme keš pro ATH
    cache = load_ath_cache()
    
    # Připravíme nové sloupce
    current_prices_list = []
    ath_list = []
    
    for idx, row in holdings_df.iterrows():
        ticker = row['ticker']
        curr_price = current_prices.get(ticker, row['avg_price']) # Pokud nemáme cenu, použijeme nákupní cenu jako zálohu
        
        ath_price = get_ath_for_ticker(ticker, curr_price, cache)
        
        current_prices_list.append(curr_price)
        ath_list.append(ath_price)
        
    # Uložíme aktualizovanou keš zpět do souboru
    save_ath_cache(cache)
    
    # Přidáme sloupce do tabulky
    holdings_df['current_price'] = current_prices_list
    holdings_df['ath'] = ath_list
    
    # Vypočítáme aktuální hodnotu portfolia a zisk/ztrátu
    holdings_df['current_value'] = holdings_df['quantity'] * holdings_df['current_price']
    holdings_df['gain_loss'] = holdings_df['current_value'] - holdings_df['total_cost']
    holdings_df['gain_loss_pct'] = (holdings_df['gain_loss'] / holdings_df['total_cost']) * 100
    
    # Vypočítáme rozdíl od ATH v procentech
    # Vzorec: ((Aktuální cena - ATH) / ATH) * 100
    # Výsledek bude záporné číslo (např. -10 % znamená, že akcie je 10 % pod svým maximem)
    holdings_df['diff_from_ath_pct'] = ((holdings_df['current_price'] - holdings_df['ath']) / holdings_df['ath']) * 100
    
    return holdings_df

if __name__ == "__main__":
    print("--- Testovací běh yfinance_helper ---")
    from data_loader import load_transactions, calculate_holdings
    
    tx = load_transactions()
    holdings = calculate_holdings(tx)
    
    # Zpracujeme všechny pozice pro přednačtení celé keše
    print("\nZpracovávám všechna aktiva v portfoliu...")
    updated = update_portfolio_prices(holdings)
    print(f"Zpracováno {len(updated)} aktiv.")
    print(updated[['ticker', 'quantity', 'avg_price', 'current_price', 'ath', 'diff_from_ath_pct']].head(10))
