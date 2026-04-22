# QUAD Wealth Portal — Global

Dashboard Streamlit para leitura macro + ferramentas de trader. Deploy em
[quad-wealth.streamlit.app](https://quad-wealth.streamlit.app/).

## Estrutura

```
market-portal/
├── app/                         # Streamlit — UI
│   ├── main.py                  # visao geral (home)
│   ├── pages/
│   │   ├── 1_Brasil.py
│   │   ├── 2_Global.py
│   │   ├── 3_Commodities.py
│   │   ├── 4_Cripto.py
│   │   ├── 5_Fundamentos.py
│   │   ├── 6_Watchlist.py
│   │   ├── 7_Noticias.py
│   │   └── 8_Monitor_Diario.py  # <-- nova: calendario + options flow + truflation
│   ├── components/
│   ├── services/                # data providers (yfinance, stooq, brapi, bcb...)
│   └── utils/
│
├── collectors/                  # Monitor Diario — scrapers/clients dos jobs 2x/dia
│   ├── economic_calendar.py
│   ├── unusual_whales.py
│   └── truflation.py
├── scheduler/
│   └── runner.py                # CLI agendado no Windows Task Scheduler
├── storage/
│   ├── db.py                    # conexao SQLite + migrations runner
│   └── migrations/              # schemas SQL
├── recon/                       # dumps de reconhecimento (endpoints UW, etc.)
├── data/                        # DB SQLite (gitignored)
├── logs/                        # logs do scheduler (gitignored)
├── tests/
│
├── config.yaml                  # config estatica (tickers, horarios, etc.)
├── .env.example                 # copiar para .env e preencher
├── requirements.txt
└── README.md
```

## Setup local

```bash
python -m venv .venv
.venv\Scripts\activate            # Windows
pip install -r requirements.txt
python -m playwright install chromium   # so para Monitor Diario (secao UW)

cp .env.example .env              # editar com suas chaves
streamlit run app/main.py
```

## Monitor Diario — operacao

### Inicializar DB

```bash
python -m storage.db              # aplica migrations idempotente
```

### Executar coleta manual

```bash
python -m scheduler.runner                      # todas as secoes
python -m scheduler.runner --only truflation    # so Truflation
```

### Agendar no Windows Task Scheduler

Task Scheduler > Create Task:

- **Program:**    `C:\Users\julio\Projetos\clientes\market-portal\.venv\Scripts\python.exe`
- **Arguments:**  `-m scheduler.runner`
- **Start in:**   `C:\Users\julio\Projetos\clientes\market-portal`
- **Triggers:**   Daily, 08:30 e 18:30 (fuso America/Sao_Paulo)
- **Settings:**   "Run whether user is logged on or not" + "Run with highest privileges"

### Debugar uma secao stale

1. Na UI do Monitor Diario, badge "stale" mostra idade em horas.
2. `logs/scheduler-YYYY-MM-DD.log` tem stack trace completo.
3. `sqlite3 data/monitor_diario.db 'SELECT * FROM scheduler_runs ORDER BY id DESC LIMIT 5'` pra ver historico de runs.
4. Rodar manual: `python -m scheduler.runner --only <secao>`.

## Testes

```bash
pytest -q
```
