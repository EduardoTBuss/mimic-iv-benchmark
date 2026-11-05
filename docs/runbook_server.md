# Runbook do servidor

Servidor principal: **x299** (`ssh x299`). Reserva pronta: **Q-FLEX** (`/c/Windows/System32/OpenSSH/ssh.exe qflex`,
chave com passphrase no ssh-agent do Windows). Em ambos, tudo fica em `~/mimic-iv-benchmark/` (permissão 700):

```
~/mimic-iv-benchmark/
  code/          checkout do commit implantado (git bundle) + .venv (requirements-lock.txt com hashes)
  data/zip/      mimic-iv-ed-2.2.zip (SHA256 d17bbf2e…)        <- dado credenciado, nunca sai daqui
  data/extracted/
  outputs/       prepared/<hash>/private (dado limpo, partições), campaigns/<id>/ (tarefas, tabelas, logs)
  reports/       relatórios agregados (mascarados)
  launch-logs/   saída do run-all lançado em segundo plano
```

## Implantar / atualizar o código (do notebook)

```bash
bash scripts/deploy_remote.sh x299 /c/datasets/mimic-iv-ed/zip/mimic-iv-ed-2.2.zip
SSH=/c/Windows/System32/OpenSSH/ssh.exe SCP=/c/Windows/System32/OpenSSH/scp.exe \
  bash scripts/deploy_remote.sh qflex /c/datasets/mimic-iv-ed/zip/mimic-iv-ed-2.2.zip
```

Recusa árvore suja. A campanha principal (`tag: main`) também recusa rodar com árvore suja.

## Lançar, acompanhar, controlar

```bash
ssh x299
cd ~/mimic-iv-benchmark/code
bash scripts/launch_bg.sh x299                          # sem tmux no x299: usa nohup setsid; log em ~/mimic-iv-benchmark/launch-logs
make status PROFILE=x299                                 # progresso, ETA, falhas, temperatura
tail -f ~/mimic-iv-benchmark/launch-logs/run-all-*.log
```

Controle ao vivo, sem reiniciar: editar `~/mimic-iv-benchmark/outputs/campaigns/<id>/control.yaml`
(`max_workers: N`, `pause: true|false`). Parar de vez: `kill <pid do scheduler>` (SIGTERM): os workers
são terminados e as tarefas voltam a pendentes; relançar retoma de onde parou (trials journalados).

Travas automáticas antes de cada lançamento: RAM livre, disco livre, carga de 1 min, temperatura da CPU
(x299: não lança acima de 78 °C; suspende todos os workers acima de 88 °C até esfriar para < 73 °C),
no máximo 1 RF e 1 ExtraTrees simultâneos no x299 (2 no Q-FLEX). Falha de tarefa: até 3 tentativas;
depois fica `failed` com `error.json` e aparece no status e no `summary.md`.

## Se o x299 cair

1. Sintomas: SSH com `Connection reset`, segfaults (ver `Brain/wiki/servidor-x299.md`). Só o Bruno reinicia.
2. Telemetria: `~/diag_x299/caixapreta_*.csv` (religar após boot:
   `cd ~/diag_x299 && nohup setsid python3 caixapreta.py ~/diag_x299 >/dev/null 2>&1 < /dev/null &`).
3. Depois do reboot: relançar o mesmo comando; a campanha retoma (tarefas DONE são puladas).
4. Se não voltar a tempo: rodar no **Q-FLEX** (já implantado). A campanha começa do zero lá (diretórios
   separados), ou continua só as seeds faltantes: `--seeds 6,7,8,9,10`. Resultados das duas máquinas
   têm o mesmo id de campanha (mesma configuração científica) e podem ser reunidos; os tempos ficam
   separados por host no relatório.

## Trazer resultados para o notebook (sem `private/`)

```bash
bash scripts/fetch_results.sh x299 <campaign-id>
```

Copia `outputs/campaigns/<id>` sem nenhum `private/` para `outputs/remote/x299/` (gitignored) e o
relatório agregado para `reports/campaigns/<id>/` (pode ir ao git).
