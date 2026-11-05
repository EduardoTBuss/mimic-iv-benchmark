# Governança de dados (PhysioNet DUA)

MIMIC-IV-ED v2.2 é dado credenciado (PhysioNet Credentialed Health Data License 1.5.0 + DUA 1.5.0,
treinamento CITI "Data or Specimens Only Research"). Regras deste projeto:

## Regra zero

1. **Nenhum dado no git.** Nem linha, nem `subject_id`/`stay_id`, nem predição por estadia, nem
   linha excluída, nem modelo treinado. O repositório só tem código, configuração e relatórios
   **agregados** com máscara de células pequenas.
2. **Dados fora do repositório**: notebook `C:\datasets\mimic-iv-ed\` (zip + extraído);
   servidores `~/ed-triage/data/` com permissão 700. A CLI aplica `umask 077` no Linux.
3. **Nada de LLM/serviço online lendo dado.** O assistente (Claude Code) só vê saídas
   agregadas de scripts (contagens, percentuais, quantis, métricas). A política do PhysioNet
   (18/04/2023) proíbe enviar dados a APIs de terceiros como a OpenAI; por isso **Codex e
   Antigravity/Gemini não são usados neste projeto**. O Claude é citado pelo PhysioNet como
   opção aceitável, mas mantemos a regra mais restritiva (só agregados).
4. **Células pequenas**: contagens de 1 a 10 aparecem como `<11` em tudo que sai de
   `outputs/` (relatórios, figuras, git); percentuais derivados delas viram `—`.
5. **Se algum passo exigir olhar linhas**, ele não é feito pelo assistente: o Eduardo roda e
   relata o agregado.
6. **Servidores**: só contas pessoais (Q-FLEX `etbuss`; x299 `eduardobuss` apenas como reserva).
   Nunca a conta compartilhada `alunospcv2026` do gacig6. Nada em `/tmp`.

## Onde cada coisa fica

| Artefato | Local | Git? |
|---|---|---|
| zip e CSVs originais | `C:\datasets\mimic-iv-ed\`, `~/ed-triage/data/` | nunca |
| dado limpo, linhas excluídas, partições | `outputs/prepared/<hash>/private/` | nunca |
| predições por estadia, modelos | `outputs/campaigns/<id>/**/private/` | nunca |
| métricas por tarefa/seed, HPO, tempos (agregados) | `outputs/campaigns/<id>/tables/` | não (ficam com a campanha) |
| relatórios agregados mascarados | `reports/` | sim |

## Verificações automáticas

- `scripts/check_gitignore.sh`: cria arquivos-isca (`*.csv`, `*.parquet`, `private/`, `outputs/`,
  `predictions*`, `*.joblib`…) e falha se o git não ignorar algum. Roda no CI.
- `.githooks/pre-commit`: bloqueia extensões de dado, arquivos > 2 MB e conteúdo com cara de
  linhas `subject_id,stay_id` do MIMIC.
- O loader nunca lê `chiefcomplaint` e valida o schema contra a documentação da v2.2.
