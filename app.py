import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from data_loader import load_transactions, calculate_holdings, calculate_closed_positions_fifo
from yfinance_helper import update_portfolio_prices, fetch_current_prices, adjust_transactions_for_splits, fetch_market_caps, fetch_sectors
from manual_tx_store import load_manual_store, save_manual_store, add_manual_transaction, edit_transaction, delete_transaction

# Nastavení stránky Streamlitu
st.set_page_config(
    page_title="Stock Portfolio Manager",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CUSTOM CSS PRO PREMIUM VZHLED (Educational) ---
# Tímto injektujeme vlastní CSS do aplikace, abychom upravili výchozí vzhled Streamlitu.
# Vytvoříme moderní tmavý vzhled s jemnými stíny a zaoblenými rohy pro karty (glassmorphism styl).
st.markdown("""
<style>
    /* Styling pro hlavní kontejner karet */
    .metric-card {
        background-color: #1e222b;
        border: 1px solid #2e3440;
        border-radius: 12px;
        padding: 20px;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        text-align: center;
        transition: transform 0.2s ease-in-out;
    }
    .metric-card:hover {
        transform: translateY(-4px);
        border-color: #4c566a;
    }
    .metric-title {
        font-size: 14px;
        color: #88c0d0;
        font-weight: 600;
        margin-bottom: 8px;
        text-transform: uppercase;
        letter-spacing: 0.8px;
    }
    .metric-value {
        font-size: 26px;
        font-weight: 700;
        color: #eceff4;
        margin-bottom: 4px;
    }
    .metric-delta {
        font-size: 14px;
        font-weight: 600;
    }
    .delta-plus {
        color: #a3be8c; /* Zelená pro zisk */
    }
    .delta-minus {
        color: #bf616a; /* Červená pro ztrátu */
    }
</style>
""", unsafe_allow_html=True)

# --- NAČÍTÁNÍ DATA S KEŠOVÁNÍM ---
# Streamlit používá kešování, aby nemusel při každé interakci uživatele znovu spouštět těžké výpočty.
# @st.cache_data říká: pokud se nezměnily vstupní CSV soubory, načti výsledek z paměti.
@st.cache_data(ttl=600)  # Keš vyprší po 10 minutách (600 s)
def get_portfolio_data(_force_refresh=2):
    try:
        # 1. Načteme transakce z CSV souborů
        transactions = load_transactions()
        
        # 2. Upravíme transakce o splity akcií
        transactions = adjust_transactions_for_splits(transactions)
        
        # 3. Vypočítáme aktuálně držené akcie (množství, průměrná nákupní cena)
        holdings = calculate_holdings(transactions)
        
        # 4. Získáme aktuální ceny a ATH
        holdings_updated = update_portfolio_prices(holdings)
        
        # 5. Načteme aktuální ceny pro obohacení jednotlivých transakcí
        tickers = list(holdings_updated['ticker'].unique())
        current_prices = fetch_current_prices(tickers)
        
        # 5b. Načteme tržní kapitalizaci pro všechny tickery
        market_caps = fetch_market_caps(tickers)
        holdings_updated['market_cap'] = holdings_updated['ticker'].map(market_caps)

        # 5c. Načteme sektor pro každý ticker
        # Sektor (např. Technology, Healthcare) stáhneme z Yahoo Finance (.info["sector"]).
        # ETF nebo fondy sektor nemají – pro ně vrátíme "Ostatní".
        sectors = fetch_sectors(tickers)
        holdings_updated['sector'] = holdings_updated['ticker'].map(sectors)
        
        # 6. Obohatíme transakce o aktuální ceny a spočítáme rozdíly
        # Přidáme sloupec s nákupní/prodejní cenou za 1 kus
        transactions['tx_price_per_share'] = transactions['Quote amount'] / transactions['Base amount']
        if 'Original amount' in transactions.columns:
            transactions['original_price_per_share'] = transactions['Quote amount'] / transactions['Original amount']
        else:
            transactions['original_price_per_share'] = transactions['tx_price_per_share']
            transactions['Original amount'] = transactions['Base amount']
            
        transactions['current_price'] = transactions['Ticker'].map(current_prices)
        
        # Vypočítáme procentuální rozdíl ceny transakce od aktuální ceny
        # Vzorec: ((Aktuální cena - Cena transakce) / Cena transakce) * 100
        transactions['diff_pct'] = ((transactions['current_price'] - transactions['tx_price_per_share']) / transactions['tx_price_per_share']) * 100
        
        # Vypočítáme absolutní rozdíl v hodnotě
        transactions['diff_value'] = (transactions['current_price'] - transactions['tx_price_per_share']) * transactions['Base amount']
        
        # 7. Vypočítáme uzavřené pozice metodou FIFO
        closed_positions = calculate_closed_positions_fifo(transactions)
        
        return transactions, holdings_updated, closed_positions
    except Exception as e:
        st.error(f"Nepodařilo se načíst data portfolia: {e}")
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()

# --- SIDEBAR (Boční panel) ---
with st.sidebar:
    st.title("📈 Nastavení")
    st.write("Vítej v aplikaci pro správu tvého akciového portfolia!")
    
    # Tlačítko pro vymazání keše a znovunačtení cen
    if st.button("🔄 Aktualizovat data (Znovunačíst ceny)", use_container_width=True):
        st.cache_data.clear()
        st.rerun()
        
    st.divider()
    
    # Výukový box (Educational panel)
    st.subheader("🎓 Jak to funguje?")
    st.info("""
    **Metoda WACP (Průměrná cena)**
    Průměrná nákupní cena je počítána váženým průměrem. Pokud koupíš 1 akcii za 100 USD a později 1 za 200 USD, tvoje průměrná cena je **150 USD**. Prodej množství snižuje, ale průměrnou cenu nemění.
    
    **Rozdíl od ATH (All-Time High)**
    Tento ukazatel ti ukazuje, jak moc je akcie aktuálně vyklesaná od svého maxima za posledních 15 let. Skvělý nástroj pro strategii "Buy the Dip" (nákup ve slevě).
    
    **Rozdíl u transakcí**
    U každé transakce porovnáváme historickou cenu nákupu/prodeje s aktuální cenou na trhu. Hned vidíš, které obchody se ti povedly nejvíce.
    """)

def format_market_cap(val):
    """
    Formátuje tržní kapitalizaci do čitelného zkráceného tvaru.
    Příklady: 3.45T, 456B, 78.1M, N/A
    """
    if pd.isna(val) or val is None:
        return "N/A"
    val = float(val)
    if val >= 1e12:
        return f"{val / 1e12:,.2f} T"
    elif val >= 1e9:
        return f"{val / 1e9:,.2f} B"
    elif val >= 1e6:
        return f"{val / 1e6:,.2f} M"
    else:
        return f"{val:,.0f}"

# Načteme data
transactions_df, holdings_df, closed_positions_df = get_portfolio_data()

if transactions_df.empty or holdings_df.empty:
    st.warning("Čekám na platná data. Ujisti se, že soubory `delta_*.csv` jsou ve složce projektu.")
    st.stop()


# --- HLAVNÍ STRÁNKA ---
st.title("📊 Přehled akciového portfolia")
try:
    from zoneinfo import ZoneInfo
    current_time = datetime.now(ZoneInfo("Europe/Prague"))
except Exception:
    current_time = datetime.now()
st.write(f"Poslední aktualizace cen: {current_time.strftime('%d.%m.%Y v %H:%M:%S')}")

# --- FILTRY ---
# Uživatel může filtrovat podle brokera
brokers = ["Všichni"] + list(holdings_df['broker'].unique())
selected_broker = st.selectbox("Vyber brokera pro filtraci:", brokers)

# Filtrujeme DataFrame podle vybraného brokera
if selected_broker != "Všichni":
    filtered_holdings = holdings_df[holdings_df['broker'] == selected_broker].copy()
    filtered_transactions = transactions_df[transactions_df['Broker_File'] == selected_broker].copy()
else:
    filtered_holdings = holdings_df.copy()
    filtered_transactions = transactions_df.copy()

# --- TABS (Záložky) ---
tab_dash, tab_holdings, tab_watchlist, tab_tx = st.tabs(["🏠 Celkový přehled", "📂 Aktuální pozice", "👁 Watchlist", "📜 Historie transakcí"])

# ==================== TAB 1: DASHBOARD ====================
with tab_dash:
    st.subheader("Shrnutí portfolia")
    
    # Protože uživatel chtěl zachovat originální měny, rozdělíme shrnutí podle měn (USD, CZK, EUR)
    currencies = filtered_holdings['currency'].unique()
    
    # Vytvoříme sloupcový layout pro jednotlivé měny
    cols = st.columns(len(currencies))
    
    for i, curr in enumerate(currencies):
        curr_holdings = filtered_holdings[filtered_holdings['currency'] == curr]
        total_cost = curr_holdings['total_cost'].sum()
        current_value = curr_holdings['current_value'].sum()
        gain_loss = current_value - total_cost
        gain_loss_pct = (gain_loss / total_cost * 100) if total_cost > 0 else 0
        
        # Color coding pro zisk/ztrátu
        delta_class = "delta-plus" if gain_loss >= 0 else "delta-minus"
        sign = "+" if gain_loss >= 0 else ""
        
        with cols[i]:
            # HTML karta s naším custom CSS stylem
            st.markdown(f"""
            <div class="metric-card">
                <div class="metric-title">Pozice v {curr}</div>
                <div class="metric-value">{current_value:,.2f} {curr}</div>
                <div style="font-size: 13px; color: #4c566a; margin-bottom: 8px;">Investováno: {total_cost:,.2f} {curr}</div>
                <div class="metric-delta {delta_class}">
                    Celkem: {sign}{gain_loss:,.2f} {curr} ({sign}{gain_loss_pct:.2f}%)
                </div>
            </div>
            """, unsafe_allow_html=True)
            
    st.divider()
    
    # Grafy alokace pomocí Plotly
    st.subheader("Alokace aktiv")
    g_col1, g_col2 = st.columns(2)
    
    with g_col1:
        # Graf 1: Distribuce podle brokerů (pouze pokud máme zobrazené všechny)
        broker_dist = filtered_holdings.groupby('broker')['current_value'].sum().reset_index()
        fig_broker = px.pie(
            broker_dist, 
            values='current_value', 
            names='broker', 
            title='Podíl brokerů na hodnotě portfolia',
            color_discrete_sequence=px.colors.qualitative.Pastel
        )
        fig_broker.update_layout(template="plotly_dark")
        st.plotly_chart(fig_broker, use_container_width=True)
        
    with g_col2:
        # Graf 2: Top 10 největších pozic v portfoliu
        top_positions = filtered_holdings.sort_values(by='current_value', ascending=False).head(10)
        fig_positions = px.bar(
            top_positions,
            x='ticker',
            y='current_value',
            color='broker',
            title='Top 10 největších pozic',
            labels={'current_value': 'Aktuální hodnota', 'ticker': 'Akcie'},
            color_discrete_sequence=px.colors.qualitative.Safe
        )
        fig_positions.update_layout(template="plotly_dark")
        st.plotly_chart(fig_positions, use_container_width=True)

    # --- GRAF SEKTORŮ ---
    # Koláčový graf zobrazuje, jak jsou tvé investice rozloženy mezi sektory ekonomiky.
    # Hodnoty v grafu jsou aktuální hodnoty pozic (current_value), ne náklady nákupu.
    st.subheader("Rozložení portfolia podle sektorů")

    if 'sector' in filtered_holdings.columns:
        sector_dist = (
            filtered_holdings
            .groupby('sector')['current_value']
            .sum()
            .reset_index()
            .rename(columns={'sector': 'Sektor', 'current_value': 'Aktuální hodnota'})
        )
        sector_dist = sector_dist[sector_dist['Aktuální hodnota'] > 0]

        if not sector_dist.empty:
            # Detailní hover: zobrazíme i konkrétní tickery v daném sektoru
            sector_tickers = (
                filtered_holdings
                .groupby('sector')['ticker']
                .apply(lambda x: ', '.join(sorted(x.unique())))
                .reset_index()
                .rename(columns={'sector': 'Sektor', 'ticker': 'Akcie'})
            )
            sector_dist = sector_dist.merge(sector_tickers, on='Sektor', how='left')

            fig_sectors = px.pie(
                sector_dist,
                values='Aktuální hodnota',
                names='Sektor',
                title='Alokace portfolia podle sektorů (dle aktuální hodnoty)',
                hover_data=['Akcie'],
                color_discrete_sequence=px.colors.qualitative.Vivid
            )
            fig_sectors.update_traces(
                textposition='inside',
                textinfo='percent+label',
                hovertemplate=(
                    '<b>%{label}</b><br>'
                    'Hodnota: %{value:,.2f}<br>'
                    'Podíl: %{percent}<br>'
                    'Akcie: %{customdata[0]}<extra></extra>'
                )
            )
            fig_sectors.update_layout(
                template="plotly_dark",
                legend=dict(orientation="v", yanchor="middle", y=0.5, xanchor="left", x=1.02)
            )
            st.plotly_chart(fig_sectors, use_container_width=True)
        else:
            st.info("Žádná data pro graf sektorů.")
    else:
        st.info("Informace o sektorech nejsou k dispozici – zkus aktualizovat data tlačítkem v levém panelu.")

# ==================== TAB 2: HOLDINGS (AKTUÁLNÍ POZICE) ====================
with tab_holdings:
    st.subheader("Přehled držených akcií")
    st.write("Tato tabulka ukazuje tvé otevřené pozice. Tabulka je **automaticky seřazena podle rozdílu od All-Time High (ATH) vzestupně** (akcie nejvíce propadlé od svého maxima jsou nahoře).")

    # Agregace: sloučíme stejné tickery od různých brokerů do jednoho řádku.
    # Ve sloupci Broker vypíšeme všechny brokery oddělené čárkou.
    display_holdings = filtered_holdings.copy()

    merged = display_holdings.groupby(['ticker', 'currency'], sort=False).agg(
        broker=('broker', lambda x: ', '.join(sorted(x.unique()))),
        quantity=('quantity', 'sum'),
        total_cost=('total_cost', 'sum'),
        current_value=('current_value', 'sum'),
        current_price=('current_price', 'first'),  # stejná cena pro všechny brokery
        ath=('ath', 'first'),                       # stejné ATH
        market_cap=('market_cap', 'first'),          # tržní kapitalizace
    ).reset_index()

    # Přepočítáme odvozené sloupce ze souhrnných hodnot
    merged['avg_price'] = merged['total_cost'] / merged['quantity']
    merged['gain_loss'] = merged['current_value'] - merged['total_cost']
    merged['gain_loss_pct'] = (merged['gain_loss'] / merged['total_cost'] * 100).where(merged['total_cost'] > 0, 0)
    merged['diff_from_ath_pct'] = ((merged['current_price'] - merged['ath']) / merged['ath'] * 100).where(merged['ath'] > 0, 0)



    # Seřadíme tabulku podle rozdílu od ATH (diff_from_ath_pct)
    merged = merged.sort_values(by='diff_from_ath_pct', ascending=True)

    # Přejmenujeme sloupce, aby byly srozumitelné pro uživatele
    merged = merged.rename(columns={
        'broker': 'Broker',
        'ticker': 'Akcie',
        'quantity': 'Množství',
        'avg_price': 'Prům. cena nákupu',
        'current_price': 'Aktuální cena',
        'total_cost': 'Celkové náklady',
        'current_value': 'Aktuální hodnota',
        'gain_loss': 'Zisk / Ztráta',
        'gain_loss_pct': 'Zisk / Ztráta (%)',
        'ath': 'All-Time High (15y)',
        'diff_from_ath_pct': 'Rozdíl od ATH (%)',
        'currency': 'Měna',
        'market_cap': 'Tržní kap.'
    })

    # Zformátujeme a zobrazíme tabulku
    st.dataframe(
        merged[[
            'Broker', 'Akcie', 'Množství', 'Měna',
            'Prům. cena nákupu', 'Aktuální cena',
            'Celkové náklady', 'Aktuální hodnota',
            'Zisk / Ztráta', 'Zisk / Ztráta (%)',
            'All-Time High (15y)', 'Rozdíl od ATH (%)',
            'Tržní kap.'
        ]].style.format({
            'Množství': '{:,.4f}',
            'Prům. cena nákupu': '{:,.2f}',
            'Aktuální cena': '{:,.2f}',
            'Celkové náklady': '{:,.2f}',
            'Aktuální hodnota': '{:,.2f}',
            'Zisk / Ztráta': '{:,.2f}',
            'Zisk / Ztráta (%)': '{:+.2f} %',
            'All-Time High (15y)': '{:,.2f}',
            'Rozdíl od ATH (%)': '{:+.2f} %',
            'Tržní kap.': format_market_cap
        }).set_properties(
            subset=['Akcie'],
            **{'color': '#88c0d0', 'font-weight': 'bold', 'background-color': '#1a2332'}
        ).background_gradient(
            subset=['Rozdíl od ATH (%)'],
            cmap='RdYlGn',
            vmin=-50.0,
            vmax=0.0
        ),
        use_container_width=True,
        height=500
    )


# ==================== TAB 3: WATCHLIST ====================
with tab_watchlist:
    st.subheader("👁 Watchlist")
    st.write("Sleduj akcie z tvého portfolia i další tituly na jednom místě. "
             "Přidej tickery oddělené čárkou do pole níže.")

    # Textové pole pro ruční přidání tickerů (uložené v session_state pro perzistenci)
    extra_tickers_input = st.text_input(
        "Přidat tickery (oddělené čárkou):",
        value=st.session_state.get("watchlist_extra", ""),
        placeholder="např. MSFT, GOOGL, TSLA",
        key="watchlist_input"
    )
    # Uložíme do session_state, aby se zachovaly mezi reruns
    st.session_state["watchlist_extra"] = extra_tickers_input

    # --- PŘEPSÁNÍ ATH ---
    with st.expander("⚙️ Ruční oprava ATH (All-Time High)"):
        st.write("Pokud ti Yahoo Finance vrací chybnou hodnotu ATH (např. kvůli reverznímu splitu u VELO), můžeš ji tady přepsat na reálnou hodnotu.")
        
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            ath_override_ticker = st.text_input("Ticker (např. VELO)", key="ath_o_ticker")
        with c2:
            ath_override_value = st.number_input("Nová hodnota ATH", min_value=0.0, value=10.0, format="%.2f", key="ath_o_val")
        with c3:
            st.write("") # mezera pro zarovnani tlacitek
            st.write("")
            col_b1, col_b2 = st.columns(2)
            with col_b1:
                if st.button("Uložit ATH", use_container_width=True):
                    if ath_override_ticker:
                        tck = ath_override_ticker.upper().strip()
                        store = load_manual_store()
                        from manual_tx_store import set_ath_override
                        set_ath_override(store, tck, ath_override_value)
                        save_manual_store(store)
                        st.success(f"ATH pro {tck} nastaveno na {ath_override_value}.")
                        st.cache_data.clear()
                        st.rerun()
            with col_b2:
                if st.button("Smazat", use_container_width=True):
                    if ath_override_ticker:
                        tck = ath_override_ticker.upper().strip()
                        store = load_manual_store()
                        from manual_tx_store import remove_ath_override
                        remove_ath_override(store, tck)
                        save_manual_store(store)
                        st.warning(f"Ruční ATH pro {tck} bylo smazáno.")
                        st.cache_data.clear()
                        st.rerun()

    # Parsujeme ručně zadané tickery
    extra_tickers = [t.strip().upper() for t in extra_tickers_input.split(",") if t.strip()]

    # Základ watchlistu: unikátní tickery ze všech transakcí (i uzavřených)
    portfolio_tickers = list(transactions_df['Ticker'].unique())

    # Sloučíme a odstraníme duplicity (zachováme pořadí: portfolio první, pak ruční)
    all_watchlist_tickers = list(dict.fromkeys(portfolio_tickers + extra_tickers))

    if all_watchlist_tickers:
        # --- Připravíme data pro watchlist tabulku ---
        # Pro tickery z portfolia máme data v holdings_df, pro nové musíme stáhnout
        existing_data = holdings_df.groupby('ticker', sort=False).agg(
            currency=('currency', 'first'),
            current_price=('current_price', 'first'),
            ath=('ath', 'first'),
            market_cap=('market_cap', 'first'),
        ).reset_index()

        existing_tickers_set = set(existing_data['ticker'].tolist())
        new_tickers = [t for t in extra_tickers if t not in existing_tickers_set]

        # Stáhneme data pro nové tickery (pokud existují)
        if new_tickers:
            from yfinance_helper import get_ath_for_ticker, load_ath_cache, save_ath_cache
            new_prices = fetch_current_prices(new_tickers)
            new_mcaps = fetch_market_caps(new_tickers)
            ath_cache = load_ath_cache()

            new_rows = []
            for t in new_tickers:
                price = new_prices.get(t)
                if price is None:
                    # Ticker neexistuje nebo nemá data — přeskočíme s varováním
                    st.warning(f"Ticker **{t}** nebyl nalezen na Yahoo Finance.")
                    continue
                ath_val = get_ath_for_ticker(t, price, ath_cache)
                new_rows.append({
                    'ticker': t,
                    'currency': 'USD',  # Výchozí měna pro ruční tickery
                    'current_price': price,
                    'ath': ath_val,
                    'market_cap': new_mcaps.get(t),
                })
            save_ath_cache(ath_cache)

            if new_rows:
                new_data = pd.DataFrame(new_rows)
                watchlist_data = pd.concat([existing_data, new_data], ignore_index=True)
            else:
                watchlist_data = existing_data.copy()
        else:
            watchlist_data = existing_data.copy()

        # Filtrujeme pouze tickery, které jsou v all_watchlist_tickers
        watchlist_data = watchlist_data[watchlist_data['ticker'].isin(all_watchlist_tickers)].copy()

        # Vypočítáme odvozené sloupce
        watchlist_data['diff_from_ath_pct'] = (
            (watchlist_data['current_price'] - watchlist_data['ath']) / watchlist_data['ath'] * 100
        ).where(watchlist_data['ath'] > 0, 0)


        # Seřadíme podle rozdílu od ATH
        watchlist_data = watchlist_data.sort_values(by='diff_from_ath_pct', ascending=True)

        # Přejmenujeme sloupce
        watchlist_display = watchlist_data.rename(columns={
            'ticker': 'Akcie',
            'currency': 'Měna',
            'current_price': 'Aktuální cena',
            'ath': 'All-Time High (15y)',
            'diff_from_ath_pct': 'Rozdíl od ATH (%)',
            'market_cap': 'Tržní kap.'
        })

        st.dataframe(
            watchlist_display[[
                'Akcie', 'Měna', 'Aktuální cena',
                'All-Time High (15y)', 'Rozdíl od ATH (%)',
                'Tržní kap.'
            ]].style.format({
                'Aktuální cena': '{:,.2f}',
                'All-Time High (15y)': '{:,.2f}',
                'Rozdíl od ATH (%)': '{:+.2f} %',
                'Tržní kap.': format_market_cap
            }).set_properties(
                subset=['Akcie'],
                **{'color': '#88c0d0', 'font-weight': 'bold', 'background-color': '#1a2332'}
            ).background_gradient(
                subset=['Rozdíl od ATH (%)'],
                cmap='RdYlGn',
                vmin=-50.0,
                vmax=0.0
            ),
            use_container_width=True,
            height=500
        )
    else:
        st.info("Žádné tickery k zobrazení. Přidej tickery do pole výše.")


# ==================== TAB 4: TRANSACTIONS (HISTORIE) ====================
with tab_tx:
    st.subheader("Historie transakcí")

    # --- MANUÁLNÍ ZADÁVÁNÍ A ÚPRAVA TRANSAKCÍ ---
    with st.expander("➕ Přidat / ✏️ Upravit transakci", expanded=False):
        st.write("Zde můžeš přidávat nové transakce, případně upravit nebo smazat ty existující.")
        
        # Výběr akce
        action = st.radio("Akce:", ["Přidat novou", "Upravit / Smazat existující"], horizontal=True)
        
        store = load_manual_store()
        all_brokers = list(transactions_df['Broker_File'].unique()) if not transactions_df.empty else ["Manual"]
        if "Manual" not in all_brokers:
            all_brokers.append("Manual")

        if action == "Přidat novou":
            with st.form("add_tx_form"):
                col1, col2 = st.columns(2)
                with col1:
                    date_val = st.date_input("Datum", value=datetime.today())
                    time_val = st.time_input("Čas", value=datetime.now().time())
                    broker_val = st.selectbox("Broker", options=all_brokers, index=all_brokers.index("Manual") if "Manual" in all_brokers else 0)
                    ticker_val = st.text_input("Ticker (např. AAPL)")
                with col2:
                    way_val = st.radio("Typ", ["BUY", "SELL"], horizontal=True)
                    qty_val = st.number_input("Množství (ks)", min_value=0.00000001, value=1.0, format="%.8f")
                    price_val = st.number_input("Cena za 1 ks", min_value=0.0, value=100.0, format="%.4f")
                    currency_val = st.selectbox("Měna", ["USD", "EUR", "CZK"])

                submitted = st.form_submit_button("uložit transakci")
                if submitted:
                    if ticker_val.strip() == "":
                        st.error("Musíš zadat Ticker.")
                    else:
                        dt = datetime.combine(date_val, time_val)
                        # Vytvoření dočasného tx_id
                        import hashlib
                        key = f"{dt}|{broker_val}|{ticker_val.upper().strip()}|{way_val}|{qty_val:.8f}"
                        tx_id = "manual_" + hashlib.sha1(key.encode('utf-8')).hexdigest()[:16]
                        
                        new_tx = {
                            "tx_id": tx_id,
                            "Date": dt,
                            "Broker_File": broker_val,
                            "Ticker": ticker_val.upper().strip(),
                            "Way": way_val,
                            "Base amount": qty_val,
                            "Quote amount": qty_val * price_val,
                            "Quote currency": currency_val,
                            "_manually_edited": True
                        }
                        
                        add_manual_transaction(store, new_tx)
                        save_manual_store(store)
                        
                        # Přidat do watchlistu
                        tick = ticker_val.upper().strip()
                        current_extra = st.session_state.get("watchlist_extra", "")
                        if tick not in list(holdings_df['ticker'].unique()) and tick not in [t.strip().upper() for t in current_extra.split(",") if t.strip()]:
                            new_extra = f"{current_extra}, {tick}" if current_extra else tick
                            st.session_state["watchlist_extra"] = new_extra
                        
                        st.cache_data.clear()
                        st.rerun()

        else:
            # Editace / Mazání
            if transactions_df.empty:
                st.info("Žádné transakce k úpravě.")
            else:
                # Vytvoříme seznam pro selectbox
                tx_options = []
                # Pro usnadnění vytvoříme slovník tx_id -> row pro snadné vyhledání
                tx_dict = {}
                for idx, row in transactions_df.sort_values(by="Date", ascending=False).iterrows():
                    # Formátování: Datum - Ticker - Množství - Typ
                    lbl = f"{row['Date'].strftime('%d.%m.%Y')} | {row['Ticker']} | {row['Way']} {row['Base amount']} ks ({row.get('Broker_File','')})"
                    tx_options.append((row['tx_id'], lbl))
                    tx_dict[row['tx_id']] = row

                sel_tx_id = st.selectbox(
                    "Vyberte transakci", 
                    options=[t[0] for t in tx_options], 
                    format_func=lambda x: next(t[1] for t in tx_options if t[0] == x)
                )

                if sel_tx_id:
                    row_data = tx_dict[sel_tx_id]
                    # Parsovat existující hodnoty
                    try:
                        cur_qty = float(row_data['Base amount'])
                        cur_quote = float(row_data['Quote amount'])
                        cur_price = cur_quote / cur_qty if cur_qty > 0 else 0.0
                    except:
                        cur_qty = 1.0
                        cur_price = 100.0
                    
                    with st.form("edit_tx_form"):
                        col1, col2 = st.columns(2)
                        with col1:
                            e_date_val = st.date_input("Datum", value=row_data['Date'].date())
                            e_time_val = st.time_input("Čas", value=row_data['Date'].time())
                            # Broker option
                            b_idx = all_brokers.index(row_data.get('Broker_File', 'Manual')) if row_data.get('Broker_File', 'Manual') in all_brokers else 0
                            e_broker_val = st.selectbox("Broker", options=all_brokers, index=b_idx)
                            e_ticker_val = st.text_input("Ticker", value=row_data['Ticker'])
                        with col2:
                            w_idx = 0 if row_data['Way'] == 'BUY' else 1
                            e_way_val = st.radio("Typ", ["BUY", "SELL"], horizontal=True, index=w_idx)
                            e_qty_val = st.number_input("Množství (ks)", min_value=0.00000001, value=cur_qty, format="%.8f")
                            e_price_val = st.number_input("Cena za 1 ks", min_value=0.0, value=cur_price, format="%.4f")
                            
                            curr_opts = ["USD", "EUR", "CZK"]
                            c_idx = curr_opts.index(row_data.get('Quote currency', 'USD')) if row_data.get('Quote currency', 'USD') in curr_opts else 0
                            e_currency_val = st.selectbox("Měna", curr_opts, index=c_idx)

                        c_btn1, c_btn2 = st.columns(2)
                        with c_btn1:
                            btn_update = st.form_submit_button("Uložit změny", type="primary")
                        with c_btn2:
                            btn_delete = st.form_submit_button("🗑 Smazat transakci")
                            
                        if btn_update:
                            if e_ticker_val.strip() == "":
                                st.error("Musíš zadat Ticker.")
                            else:
                                e_dt = datetime.combine(e_date_val, e_time_val)
                                changes = {
                                    "Date": e_dt,
                                    "Broker_File": e_broker_val,
                                    "Ticker": e_ticker_val.upper().strip(),
                                    "Way": e_way_val,
                                    "Base amount": e_qty_val,
                                    "Quote amount": e_qty_val * e_price_val,
                                    "Quote currency": e_currency_val,
                                    "_manually_edited": True
                                }
                                edit_transaction(store, sel_tx_id, changes)
                                save_manual_store(store)
                                
                                tick = e_ticker_val.upper().strip()
                                current_extra = st.session_state.get("watchlist_extra", "")
                                if tick not in list(holdings_df['ticker'].unique()) and tick not in [t.strip().upper() for t in current_extra.split(",") if t.strip()]:
                                    new_extra = f"{current_extra}, {tick}" if current_extra else tick
                                    st.session_state["watchlist_extra"] = new_extra
                                    
                                st.success("Uloženo.")
                                st.cache_data.clear()
                                st.rerun()
                                
                        if btn_delete:
                            delete_transaction(store, sel_tx_id)
                            save_manual_store(store)
                            st.warning("Smazáno.")
                            st.cache_data.clear()
                            st.rerun()

    # --- PŘEPÍNAČ: Otevřené / Uzavřené pozice ---
    tx_view = st.radio(
        "Zobrazit:",
        options=["📂 Otevřené pozice (aktivní nákupy)", "✅ Uzavřené pozice (FIFO)"],
        horizontal=True,
        key="tx_view_toggle"
    )

    st.divider()

    # ---- POHLED: OTEVŘENÉ POZICE ----
    if tx_view == "📂 Otevřené pozice (aktivní nákupy)":
        st.write("Tato tabulka porovnává nákupní/prodejní ceny jednotlivých transakcí s aktuální tržní cenou. "
                 "**Výchozí řazení je podle procentuálního rozdílu od aktuální ceny.**")

        display_tx = filtered_transactions.copy()

        # Odstraníme původní sloupec 'Broker' z CSV, aby nekolidoval s naším novým sloupcem 'Broker' (přejmenovaný Broker_File)
        display_tx = display_tx.drop(columns=['Broker'], errors='ignore')

        # Přidáme sloupec s absolutní hodnotou procentuálního rozdílu pro možnost řazení
        display_tx['abs_diff_pct'] = display_tx['diff_pct'].abs()

        # Seřadíme tabulku primárně podle absolutní odchylky od aktuální ceny (největší rozdíly nahoře)
        display_tx = display_tx.sort_values(by='abs_diff_pct', ascending=False)

        # Přejmenujeme sloupce
        display_tx = display_tx.rename(columns={
            'Date': 'Datum transakce',
            'Broker_File': 'Broker',
            'Way': 'Typ',
            'Ticker': 'Akcie',
            'Original amount': 'Množství (Původní)',
            'Base amount': 'Množství (Po splitech)',
            'original_price_per_share': 'Cena (Původní)',
            'tx_price_per_share': 'Cena (Po splitech)',
            'current_price': 'Aktuální cena',
            'Quote currency': 'Měna',
            'diff_pct': 'Rozdíl vs Aktuální (%)',
            'diff_value': 'Rozdíl v hodnotě'
        })

        # DŮLEŽITÉ: datum NEPŘEVÁDÍME na string – ponecháme datetime typ,
        # aby Streamlit mohl správně řadit podle data při kliknutí na záhlaví.
        # Formát zobrazení (dd.mm.yyyy) nastavíme přes column_config.

        def highlight_sell(row):
            """Obarví celý řádek červeně, pokud je transakce typu SELL."""
            if row.get('Typ') == 'SELL':
                return ['color: #bf616a'] * len(row)
            return [''] * len(row)

        st.dataframe(
            display_tx[[
                'Datum transakce', 'Broker', 'Akcie', 'Typ', 
                'Množství (Původní)', 'Cena (Původní)',
                'Množství (Po splitech)', 'Cena (Po splitech)', 
                'Aktuální cena', 'Měna',
                'Rozdíl vs Aktuální (%)', 'Rozdíl v hodnotě'
            ]].style.format({
                'Množství (Původní)': '{:,.4f}',
                'Cena (Původní)': '{:,.4f}',
                'Množství (Po splitech)': '{:,.4f}',
                'Cena (Po splitech)': '{:,.2f}',
                'Aktuální cena': '{:,.2f}',
                'Rozdíl vs Aktuální (%)': '{:+.2f} %',
                'Rozdíl v hodnotě': '{:+.2f}'
            }).apply(highlight_sell, axis=1
            ).set_properties(
                subset=['Akcie'],
                **{'color': '#88c0d0', 'font-weight': 'bold', 'background-color': '#1a2332'}
            ).background_gradient(
                subset=['Rozdíl vs Aktuální (%)'],
                cmap='RdYlGn',
                vmin=-50.0,
                vmax=50.0
            ),
            use_container_width=True,
            height=550,
            column_config={
                'Datum transakce': st.column_config.DatetimeColumn(
                    'Datum transakce',
                    format='DD.MM.YYYY HH:mm'
                )
            }
        )

    # ---- POHLED: UZAVŘENÉ POZICE (FIFO) ----
    else:
        st.write(
            "Tato tabulka zobrazuje **realizované (uzavřené) obchody** počítané metodou **FIFO** "
            "(First In, First Out). Každý řádek odpovídá prodeji spárovanému s nejstarším "
            "dostupným nákupem. Seřazeno od nejnovějšího prodeje."
        )

        # Filtrujeme uzavřené pozice podle brokera (pokud je vybrán konkrétní broker)
        if closed_positions_df.empty:
            st.info("Zatím žádné uzavřené pozice. Uzavřená pozice vzniká prodejem (SELL) akcií, které jsi předtím nakoupil.")
        else:
            display_closed = closed_positions_df.copy()
            if selected_broker != "Všichni":
                display_closed = display_closed[display_closed['Broker'] == selected_broker].copy()

            if display_closed.empty:
                st.info(f"Pro brokera **{selected_broker}** zatím žádné uzavřené pozice.")
            else:
                # --- Souhrnné metriky uzavřených pozic ---
                total_realized = display_closed['Realizovaný zisk/ztráta'].sum()
                total_buy_cost = display_closed['Náklady nákupu'].sum()
                total_sell_proceeds = display_closed['Výnos prodeje'].sum()
                total_realized_pct = (total_realized / total_buy_cost * 100) if total_buy_cost > 0 else 0.0
                num_trades = len(display_closed)
                winning_trades = (display_closed['Realizovaný zisk/ztráta'] > 0).sum()
                win_rate = (winning_trades / num_trades * 100) if num_trades > 0 else 0.0

                delta_class = "delta-plus" if total_realized >= 0 else "delta-minus"
                sign = "+" if total_realized >= 0 else ""

                # Zobrazíme souhrnné karty
                m_col1, m_col2, m_col3, m_col4 = st.columns(4)
                with m_col1:
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-title">Realizovaný zisk/ztráta</div>
                        <div class="metric-value {delta_class}">{sign}{total_realized:,.2f}</div>
                        <div class="metric-delta {delta_class}">{sign}{total_realized_pct:.2f} %</div>
                    </div>""", unsafe_allow_html=True)
                with m_col2:
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-title">Celkové náklady nákupů</div>
                        <div class="metric-value">{total_buy_cost:,.2f}</div>
                        <div style="font-size:13px;color:#4c566a;">Celkový výnos: {total_sell_proceeds:,.2f}</div>
                    </div>""", unsafe_allow_html=True)
                with m_col3:
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-title">Počet uzavřených obchodů</div>
                        <div class="metric-value">{num_trades}</div>
                        <div style="font-size:13px;color:#4c566a;">FIFO párování</div>
                    </div>""", unsafe_allow_html=True)
                with m_col4:
                    wr_class = "delta-plus" if win_rate >= 50 else "delta-minus"
                    st.markdown(f"""
                    <div class="metric-card">
                        <div class="metric-title">Úspěšnost obchodů</div>
                        <div class="metric-value {wr_class}">{win_rate:.1f} %</div>
                        <div style="font-size:13px;color:#4c566a;">{winning_trades} ziskových z {num_trades}</div>
                    </div>""", unsafe_allow_html=True)

                st.markdown("<br>", unsafe_allow_html=True)

                # DŮLEŽITÉ: data NEPŘEVÁDÍME na string – ponecháme datetime typ
                # pro správné řazení. Formát nastavujeme přes column_config.
                st.dataframe(
                    display_closed[[
                        'Broker', 'Akcie', 'Měna', 'Množství',
                        'Datum nákupu', 'Nákupní cena (1 ks)',
                        'Datum prodeje', 'Prodejní cena (1 ks)',
                        'Náklady nákupu', 'Výnos prodeje',
                        'Realizovaný zisk/ztráta', 'Realizovaný zisk/ztráta (%)',
                        'Drženo dní'
                    ]].style.format({
                        'Množství': '{:,.4f}',
                        'Nákupní cena (1 ks)': '{:,.2f}',
                        'Prodejní cena (1 ks)': '{:,.2f}',
                        'Náklady nákupu': '{:,.2f}',
                        'Výnos prodeje': '{:,.2f}',
                        'Realizovaný zisk/ztráta': '{:+,.2f}',
                        'Realizovaný zisk/ztráta (%)': '{:+.2f} %',
                        'Drženo dní': '{:,.0f}'
                    }).set_properties(
                        subset=['Akcie'],
                        **{'color': '#88c0d0', 'font-weight': 'bold', 'background-color': '#1a2332'}
                    ).background_gradient(
                        subset=['Realizovaný zisk/ztráta (%)'],
                        cmap='RdYlGn',
                        vmin=-50.0,
                        vmax=50.0
                    ),
                    use_container_width=True,
                    height=550,
                    column_config={
                        'Datum nákupu': st.column_config.DatetimeColumn(
                            'Datum nákupu',
                            format='DD.MM.YYYY'
                        ),
                        'Datum prodeje': st.column_config.DatetimeColumn(
                            'Datum prodeje',
                            format='DD.MM.YYYY'
                        ),
                    }
                )
