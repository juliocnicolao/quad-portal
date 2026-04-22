-- Fase 4: GEX diario agregado (nao por strike) via Unusual Whales
-- Endpoint: /api/gex/{ticker}?timespan=1y retorna 1 ponto por dia com
-- totais de gamma/delta/charm/vanna (call + put). O shape nao eh strike-
-- level, entao criamos uma tabela separada em vez de reusar gex_snapshots.

CREATE TABLE IF NOT EXISTS gex_daily (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_collected    TEXT NOT NULL,          -- ISO8601 UTC
    ticker          TEXT NOT NULL,
    date            TEXT NOT NULL,          -- YYYY-MM-DD
    close           REAL,                   -- underlying close naquele dia
    call_gex        REAL,
    put_gex         REAL,
    call_delta      REAL,
    put_delta       REAL,
    call_charm      REAL,
    put_charm       REAL,
    call_vanna      REAL,
    put_vanna       REAL,
    UNIQUE(ticker, date)
);
CREATE INDEX IF NOT EXISTS idx_gex_daily_ticker_date ON gex_daily(ticker, date DESC);
