# Monitor Diário — guia operacional

Painel do QUAD Portal que coleta automaticamente 2×/dia (08:30 e 18:30 BRT):
calendário econômico US+BR, options flow + GEX de PBR/TLT/SPY/EWZ via
Unusual Whales, e o TruCPI-US da Truflation.

Os dados ficam no SQLite (`data/monitor_diario.db`) e são renderizados
em `pages/8_Monitor_Diario.py`.

---

## Estrutura

```
collectors/           # 1 módulo por fonte; todos expõem collect() -> dict
  economic_calendar.py   # investing.com (Playwright + anti-CF)
  unusual_whales.py      # phx.unusualwhales.com (httpx direto)
  truflation.py          # truflation.com API pública (httpx)

scheduler/
  runner.py              # CLI: python -m scheduler.runner [--only sec,sec]

scripts/
  run_monitor.bat              # wrapper invocado pelo Task Scheduler
  install_scheduler.ps1        # registra a tarefa Windows
  uninstall_scheduler.ps1      # remove a tarefa

storage/
  db.py                  # get_conn() + apply_migrations()
  migrations/            # SQL numerado, idempotente
    001_initial.sql
    002_uw_gex_daily.sql

app/pages/8_Monitor_Diario.py  # UI em 3 tabs

recon/                   # scripts de descoberta de endpoints (não rodam no scheduler)
tests/                   # pytest, 64+ testes puros
data/
  monitor_diario.db      # SQLite principal
  backups/               # snapshots VACUUM INTO diários (retidos 14d)
logs/
  scheduler_run.log            # ativo
  scheduler_run.log.YYYY-MM-DD # rotated (retidos 14d)
```

---

## Rodar localmente

### Scheduler CLI

```bash
# Todas as seções:
python -m scheduler.runner

# Só uma:
python -m scheduler.runner --only truflation
python -m scheduler.runner --only calendar,uw
```

Cada run grava uma linha em `scheduler_runs` com status consolidado.

### UI Streamlit

A página "Monitor Diário" lê apenas do DB — não dispara coletas
automáticas. Use o botão ▶ **Rodar agora** (header) para disparar
um run em background (subprocess detached).

---

## Windows Task Scheduler (automação 2×/dia)

```powershell
cd C:\Users\julio\Projetos\clientes\market-portal
powershell -ExecutionPolicy Bypass -File scripts\install_scheduler.ps1
```

Registra a tarefa `QUAD-MonitorDiario` com 2 triggers (08:30 e 18:30
hora local = BRT). Sem admin, roda como o usuário atual. Remover com
`uninstall_scheduler.ps1`.

Comandos úteis:
```powershell
Get-ScheduledTaskInfo -TaskName 'QUAD-MonitorDiario'   # último run
Start-ScheduledTask   -TaskName 'QUAD-MonitorDiario'   # rodar agora
Get-ScheduledTask     -TaskName 'QUAD-MonitorDiario'   # estado
```

---

## Configuração (`config.yaml`)

Principais chaves editáveis sem re-deploy:

| Chave                              | Default  | Efeito                                |
|------------------------------------|----------|---------------------------------------|
| `calendar.lookback_days`           | 30       | Janela passada de occurrences         |
| `calendar.lookahead_days`          | 14       | Janela futura                         |
| `calendar.request_delay_s`         | 1.5      | Pausa entre events (gentil com site)  |
| `calendar.max_retries`             | 2        | Retries em falha de Cloudflare        |
| `calendar.retry_backoff_s`         | 4.0      | Backoff linear (4s, 8s, 12s…)         |
| `calendar.events.US[]`             | lista    | Watchlist US (name + slug investing)  |
| `calendar.events.BR[]`             | lista    | Watchlist BR                          |
| `options_flow.tickers`             | [4]      | Tickers UW (PBR, TLT, SPY, EWZ)       |
| `options_flow.request_delay_seconds` | 3      | Pausa entre tickers                   |
| `truflation.api_url`               | URL      | Endpoint público (descoberto via recon) |
| `logging.retention_days`           | 14       | Logs e backups SQLite retidos (dias)  |

### Adicionar evento econômico

1. Abra `investing.com/economic-calendar/`, clique no evento
2. Pegue o slug do URL (ex.: `/economic-calendar/cpi-733` → `cpi-733`)
3. Adicione em `config.yaml`:
   ```yaml
   calendar:
     events:
       US:
         - { name: "Meu Evento", slug: "meu-evento-9999" }
   ```
4. Próxima run coleta automaticamente. Nenhum código muda.

### Adicionar ticker de opções

```yaml
options_flow:
  tickers: [PBR, TLT, SPY, EWZ, QQQ, IWM]  # adiciona QQQ e IWM
```

A UI quebra tickers em linhas de 4, então não há limite prático.

---

## Schema do DB

- `scheduler_runs` — 1 linha por execução (status, notes JSON com falhas)
- `economic_events` — `UNIQUE(event_time, country, event_name)`
- `options_flow_daily` — `UNIQUE(ticker, date)` — 5 dias por fetch acumulam
- `gex_daily` — `UNIQUE(ticker, date)` — 1Y de histórico de GEX agregado
- `gex_snapshots` — **reservada** para dados strike-level (hoje vazia;
  UW free tier só expõe agregado diário)
- `truflation_history` — `UNIQUE(date)` — 366 pontos diários

Upsert idempotente em todas: re-rodar o mesmo run não duplica nada.

---

## Observabilidade

- **Sidebar global** (todas páginas do portal): badge aparece se
  scheduler falhou / stale. Vermelho: `failed` ou idade > 48h.
  Amarelo: `partial` ou idade > 25h. Sem badge = saudável.
- **Header do Monitor**: run ID, status, timestamps, badge por seção
  com freshness do último `ts_collected` da tabela correspondente.
- **Expander "⚠️ N falha(s) no último run"**: lista slug/país/ticker +
  mensagem de erro (persistido em `scheduler_runs.notes`).
- **Log**: `logs/scheduler_run.log` (rotação diária automática).

---

## Troubleshooting

### Calendar fica `partial`
Normal. investing.com ocasionalmente devolve challenge de Cloudflare.
Retry automático (2×) resolve a maioria. Eventos que falham ficam no
expander de erros da UI; próxima run tende a pegá-los.

### `Scheduler parado há Nh` na sidebar
Checar `Get-ScheduledTaskInfo -TaskName 'QUAD-MonitorDiario'`.
`LastTaskResult`:
- `0` = sucesso
- `267009` = está rodando agora
- `267011` = nunca rodou (só depois do primeiro trigger)
- Outros = ver `logs/scheduler_run.log`

### Botão "▶ Rodar agora" não parece ter efeito
Ele dispara subprocess detached. Confira `logs/scheduler_run.log` —
a saída vai pra lá. Badges de freshness atualizam ~1-2 min depois.

### DB corrompido
Backup diário em `data/backups/monitor_diario-YYYY-MM-DD.db`
(VACUUM INTO, retido 14 dias). Restaurar é só copiar por cima.

---

## Testes

```bash
python -m pytest tests/ -q
```

Todos os parsers são puros (sem rede nem DB) — rodam em <2s. Há
também testes de infra (log rotation, vacuum, health badge thresholds).

Ao adicionar uma nova fonte, siga o padrão:
1. Recon em `recon/<fonte>_recon.py` (descobre endpoints + shape)
2. Collector em `collectors/<fonte>.py` expondo `collect() -> dict`
3. Pure parsers separados das I/O funções
4. Teste `tests/test_<fonte>_parser.py` com fixtures do recon
5. Tab na UI em `pages/8_Monitor_Diario.py`
