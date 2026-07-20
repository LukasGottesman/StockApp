\# Moje nápady pro StockApp



## 🔜 Aktuálně rozpracované
- [ ] Napojit Supabase (PostgreSQL) databázi místo CSV souborů
- [ ] Naimportovat CSV data (FIO, Revolut, XTB) do Supabase
- [ ] Nastavit Supabase klíče ve Streamlit Secrets (lokálně + cloud)

## 🚀 Budoucí: Přepis do Next.js + React (až bude čas)
- [ ] Kompletní přepis aplikace do Next.js + TypeScript
- [ ] Hosting na Vercel (zdarma, private repo, žádný cold start)
- [ ] Supabase jako databáze (už bude nastavená z aktuálního kroku)
- [ ] Moderní UI s animacemi a responzivním designem
- [ ] Přepsat Python logiku (FIFO, portfolio výpočty) do TypeScript
- [ ] Interaktivní grafy (Recharts / Chart.js)
- [ ] Formulář pro přidávání transakcí přímo v aplikaci
- [ ] PWA podpora (appka na mobilu jako nativní)

## Funkce k naprogramování

- [x] Na záložkách "Aktuální pozice" a "Watchlist" přidej do tabulek sloupec s tržní kapitalizací

- [x] Přidat na záložku "Historie transakcí" přepínač "Uzavřené/Otevřené pozice". Pozice uzavírat chronologicky metodou FIFO.

- [x] Spojit do koláčového grafu "Tržní hodnota" i "Nerealizovaný P/L" (uživatel to chce vidět na Dashboardu)
- [x] Připravit koláčový graf podle sektorů mých akcií (na záložce celkový přehled).
- [x] Na záložce "Historie transakcí" nad stávající tabulkou přidat formulář pro zadávání nových pozic (abychom nemuseli řešit přes CSV). Možnost upravit a odebrat existující transakce. Jakýkoliv ticker z transakce, který ještě není na watchlistu tam přidat automaticky.

- [x] Hodnota All-Time High u VELO není asi správně je moc velká (přidána možnost ručního přepsání)






\## Data k doplnění

\



\## Opravy a vylepšení

- Ověřit, jak aplikace zvládá splity akcií u titulů jako Apple nebo Nvidia. Už jsme začali řešit minule 26.6.2026
- **Optimalizace stahování cen:** Pokud budeme v budoucnu aplikaci migrovat na výkonnější hardware (mimo Streamlit Community Cloud), zvážit opětovné zapnutí zrychleného stahování dat přes `yfinance` ve více vláknech (`threads=True`), které jsme museli vypnout kvůli Segmentation fault.



\## Dokumentace

\- Až aplikaci doděláme budu chtít sepsat postup jejího vývoje formou výukového materiálu pro začínajícího vývojáře, s popisem každého kroku / přikazu podobně, jak jsi mi to popisoval první den 26.6., kdy jsem si stěžoval, že nevím co odsouhlasuju.



