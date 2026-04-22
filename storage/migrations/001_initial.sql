-- Monitor Diario — schema inicial
-- Timestamps sempre em UTC (ISO 8601). Conversao para America/Sao_Paulo na UI.

-- ── Controle de execucoes do scheduler ────────────────────────────────────
CREATE TABLE IF NOT EXISTS scheduler_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_started   TEXT NOT NULL,          -- ISO8601 UTC
    ts_finished  TEXT,
    status       TEXT NOT NULL,          -- running | ok | partial | failed
    sections     TEXT NOT NULL,          -- JSON: {"calendar":"ok","uw":"failed",...}
    notes        TEXT
);
CREATE INDEX IF NOT EXISTS idx_scheduler_runs_started ON scheduler_runs(ts_started DESC);

-- ── Secao 1: Calendario Economico ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS economic_events (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_collected TEXT NOT NULL,          -- ISO8601 UTC
    event_time   TEXT NOT NULL,          -- ISO8601 UTC
    country      TEXT NOT NULL,          -- US | BR
    event_name   TEXT NOT NULL,
    impact       TEXT NOT NULL,          -- high | medium | low
    forecast     REAL,
    previous     REAL,
    actual       REAL,
    surprise     REAL,                   -- actual - forecast
    surprise_pct REAL,                   -- (actual - forecast) / |forecast|
    unit         TEXT,                   -- "%", "K", "M", etc
    source       TEXT NOT NULL,          -- investing | fred | bcb | trading_economics
    source_raw   TEXT,                   -- JSON bruto pra debug
    UNIQUE(event_time, country, event_name)
);
CREATE INDEX IF NOT EXISTS idx_events_time ON economic_events(event_time DESC);
CREATE INDEX IF NOT EXISTS idx_events_country ON economic_events(country, event_time DESC);

-- ── Secao 2: Options Flow (Unusual Whales) ────────────────────────────────
CREATE TABLE IF NOT EXISTS options_flow_daily (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_collected    TEXT NOT NULL,       -- ISO8601 UTC
    ticker          TEXT NOT NULL,
    date            TEXT NOT NULL,       -- YYYY-MM-DD (trading day)
    open            REAL,
    high            REAL,
    low             REAL,
    close           REAL,
    pct_change      REAL,
    pc_ratio        REAL,                -- put/call ratio
    volume          INTEGER,             -- total options volume
    c_vol           INTEGER,             -- call volume
    p_vol           INTEGER,             -- put volume
    vol_30d_ratio   REAL,                -- vol / 30d avg
    total_oi        INTEGER,
    oi_pct          REAL,
    c_oi            INTEGER,
    p_oi            INTEGER,
    ivr             REAL,                -- IV Rank
    vol_30d         REAL,                -- realized vol 30d
    implied_30d     REAL,                -- IV 30d
    vol_60d         REAL,
    implied_60d     REAL,
    net_prem        REAL,                -- net premium (calls - puts)
    total_prem      REAL,
    source_raw_json TEXT,
    UNIQUE(ticker, date)
);
CREATE INDEX IF NOT EXISTS idx_of_ticker_date ON options_flow_daily(ticker, date DESC);

-- ── Secao 2b: Snapshots GEX por strike ────────────────────────────────────
CREATE TABLE IF NOT EXISTS gex_snapshots (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_collected        TEXT NOT NULL,   -- ISO8601 UTC
    ticker              TEXT NOT NULL,
    strike              REAL NOT NULL,
    gamma               REAL NOT NULL,
    price_at_snapshot   REAL,
    source_raw_json     TEXT
);
CREATE INDEX IF NOT EXISTS idx_gex_ticker_ts ON gex_snapshots(ticker, ts_collected DESC);

-- ── Secao 3: Truflation ───────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS truflation_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts_collected TEXT NOT NULL,          -- ISO8601 UTC
    date         TEXT NOT NULL,          -- YYYY-MM-DD
    value        REAL NOT NULL,          -- indice (ex.: 3.25)
    change_1d    REAL,
    change_7d    REAL,
    change_30d   REAL,
    source_raw   TEXT,
    UNIQUE(date)
);
CREATE INDEX IF NOT EXISTS idx_truflation_date ON truflation_history(date DESC);
