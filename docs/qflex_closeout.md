# Q-FLEX: fechamento da campanha e resultados do artigo

Estado em 08/11/2026. Este roteiro preserva o pré-registro; não inicia campanha,
treinamento, novo HPO ou seleção de seeds por desempenho.

## Estado verificado e escopo

- Inspeção operacional por SSH: 32 threads disponíveis na afinidade, 125,6 GiB
  de RAM total, 121,6 GiB disponíveis, 1.134,1 GiB livres no volume do projeto;
  carga de um minuto 0,08. São medidas pontuais de infraestrutura, não resultados.
- Python remoto 3.12.3. `code/` está em `ae4b22d03294fbbbb8128f5c4f9d2fdac3b2d34a`;
  `code-next/` em `8a831d0df55e30a7f4e51b6ff04c668507ebcfae`. Não atualizar essas
  cópias por cima; preparar uma cópia separada para o fechamento revisado.
- O checkpoint do Brain informa 810 tarefas e zero falhas na campanha
  `main-38c9f7c0a8`. Esse histórico ainda não foi confrontado com os artefatos.
- Eduardo autorizou o uso dos resultados agregados em 08/11. A condição anterior
  sobre elegibilidade deste serviço permanece sem evidência documentada; a
  confirmação foi solicitada. Nenhum resultado foi aberto nesta preparação.

As instruções que leem artefatos abaixo são para executor local autorizado.
Executar por SSH através de um serviço online não elimina a restrição. O modo
`--aggregates-only` evita entradas por paciente, mas ainda processa derivados;
não certifica a elegibilidade do serviço para recebê-los.

## 1. Preservar a evidência existente

Usar uma cópia revisada das fontes, aqui chamada `code-closeout/`. Manter os
artefatos originais sob controle do executor, sem sobrescrever resultados e sem
enviar arquivos para a conversa. O script de inventário usa somente a biblioteca
padrão, sem depender da instalação científica.

A implantação de fontes ainda precisa ser feita pelo executor. Após commit das
fontes revisadas, o script existente pode criar a cópia separada, sem passar
qualquer argumento de ZIP. No Git Bash do notebook:

```bash
CODE_DIR=code-closeout \
  SSH=/c/Windows/System32/OpenSSH/ssh.exe \
  SCP=/c/Windows/System32/OpenSSH/scp.exe \
  bash scripts/deploy_remote.sh qflex
```

Isso prepara também `.venv`; não treina nem analisa. A implantação operacional
desta sessão limitou-se aos dois arquivos de teste sintético em diretório isolado;
nenhuma cópia de produção foi atualizada.

Antes de capturar, confirmar localmente que scheduler, merges e pós-processamento
não estão escrevendo na campanha. Aguardar sua conclusão ou pausar os escritores
de forma controlada. A ferramenta detecta alterações comuns durante a leitura,
mas não substitui um snapshot atômico do sistema de arquivos.

```bash
umask 077
source_root="$HOME/mimic-iv-benchmark/code-closeout"
campaign_dir="$HOME/mimic-iv-benchmark/outputs/campaigns/main-38c9f7c0a8"
capture_dir="$HOME/mimic-iv-benchmark/closures/inventory-20261108"
mkdir -p "$HOME/mimic-iv-benchmark/closures"

python3.12 "$source_root/scripts/campaign_inventory.py" capture \
  --campaign "$campaign_dir" --destination "$capture_dir"
```

O destino deve ser novo e estar fora da campanha. Por padrão, a captura não
abre nem percorre `private/`; registra hashes de agregados e metadados. O modo
opcional `--include-private` é uma operação separada para executor autorizado;
ele lê bytes de arquivos privados e não deve ser tratado como acesso somente
a agregados. Nenhum modo imprime conteúdo clínico ou valores de métricas.

O inventário registra integridade e completude estrutural. `DONE` não comprova
Macro-F1 finito, validade de predições ou correção científica. Guardar também os
arquivos vinculados, em armazenamento privado: hashes sozinhos não permitem
recuperar bytes perdidos. Preservar o digest do inventário separadamente para
comparações futuras; ler o digest e o inventário da mesma fonte mutável não
protege contra a substituição de ambos.

```bash
# captured_digest deve vir do registro independente preservado pelo operador.
python3.12 "$source_root/scripts/campaign_inventory.py" verify \
  --campaign "$campaign_dir" --inventory "$capture_dir/inventory.json" \
  --expected-sha256 "$captured_digest" \
  --destination "$HOME/mimic-iv-benchmark/closures/verification-20261108"
```

Hash, permissões de arquivo e data local não constituem prova independente do
instante. Documentar a fonte temporal e a evidência disponível; não alegar que
este utilitário implementa armazenamento imutável ou certificação de prazo.

## 2. Conferir a regra de corte sem mudar o plano

O corte permanece **10/11/2026 às 12h BRT / 15h UTC**. Antes dele, análises são
prévias técnicas. No corte, verificar a matriz completa de primários de A:
23 combinações aplicáveis por seed, 10 seeds, Macro-F1 finito em validação e
teste. Não confundir esse requisito com a contagem global de 810 tarefas.

Um inventário antecipado parcial não comprova o maior prefixo no corte, pois
outras seeds podem completar até o prazo. Se as dez estiverem válidas e
completas antecipadamente, o teto foi atingido, mas ainda é preciso vincular os
bytes utilizados e a evidência temporal. A regra do maior prefixo 1..k, mínimo
cinco seeds, continua a do plano. Não usar scores para excluir seeds.

O código atual continua com `principal_analysis=false`: após o corte retorna
`pending_cutoff_provenance`. A ferramenta de inventário não remove esse bloqueio.
O mecanismo de aceitar evidência revisada e habilitar a análise principal ainda
precisa ser implementado/verificado separadamente. Não usar uma flag booleana,
`finished_at` ou um horário de análise informado pelo usuário como prova.

## 3. Inspecionar resultados agregados sem entradas por paciente

Na cópia revisada das fontes e no ambiente autorizado:

```bash
cd "$source_root"
PYTHONPATH=src .venv/bin/python -m triagebench analyze \
  --config configs/main.yaml --profile qflex \
  --campaign "$campaign_dir" --aggregates-only
```

Esse comando lê resultados agregados por tarefa, histórico de ajustes,
metadados e tabelas agregadas complementares existentes. Não lê o ZIP, CSVs,
dados preparados, predições por estadia, probabilidades privadas ou modelos.
Não executa treino, importância por permutação ou benchmark de custo.

As saídas ficam em `tables/stats_aggregates_only.json` na campanha e em
`reports/aggregates-only/campaigns/<id>/`, sem substituir `stats.json` e o
relatório completo. As tabelas básicas de agregação são regeneradas na campanha.
Não rodar simultaneamente à alteração desses artefatos; conferir o inventário
e registrar hashes das saídas no fechamento local.

H1, H2, erros ordinais e A−C podem usar as métricas já agregadas, dentro das
regras temporais atuais. Ausência de predições impede conferir integridade por
estadia, bootstrap por paciente, A/B no subconjunto comum, estratos e
decodificações. As omissões são explícitas; esse relatório não certifica toda a
campanha nem substitui a revisão empírica completa. A/B em testes próprios não
é evidência de diferença pareada.

## 4. Revisão local e pacote empírico do artigo

Um executor/revisor autorizado deve conferir os seguintes pontos na Q-FLEX,
com os arquivos privados permanecendo no ambiente local quando necessários:

1. Identidade científica, versões do código, matriz esperada e prefixo no prazo.
2. Busca na validação, ajustes falhos/avisos e seleção de modelos sem uso do teste.
3. H1: diferenças por seed, IC corrigido e critério conjunto registrado.
4. H2: diferenças pareadas e Holm nas seis famílias, sem alegação global.
5. Métricas versus predições; universos de teste e pareamento A/B/C; bootstrap
   por paciente quando disponível; anomalias e seções ausentes explicitadas.
6. Custo sequencial previsto, unidades e importância por permutação existentes;
   não interpretar tempos concorrentes como comparação controlada.
7. Divulgação: nenhuma linha, ID ou predição; máscara de células pequenas e de
   percentuais correspondentes; aprovação das categorias de agregados exportáveis.

Depois da autorização de transferência e revisão empírica, selecionar somente
os agregados necessários para preencher o artigo inglês de seis páginas:
tabela de desempenho principal; tabela compacta de contrastes/balanceamento e
erros; diferenças por seed/IC; matriz de confusão agregada com divulgação
verificada. Reduzir material conceitual para manter seis páginas. As conclusões
seguirão as estimativas, inclusive eventual ausência de superioridade consistente.
Nenhum valor foi escolhido ou inserido nesta preparação.

## Responsabilidades e evidências

| Frente | Responsável | Evidência necessária |
|---|---|---|
| Ferramenta de inventário | implementação separada, revisão do coordenador | testes sintéticos de alterações, ausências, corridas e escopo |
| Modo de agregados | coordenador, revisão independente de integração | guardas sintéticas de acesso e preservação de saídas completas |
| Corte e interpretação | revisão independente de desenho | plano intacto; integridade, completude e tempo separados |
| Uso dos derivados | Eduardo e ambiente autorizado | elegibilidade/categorias documentadas ou fluxo inteiramente local |
| Valores e conclusão do artigo | executor e revisor empírico autorizado | resultados verificados; revisão final ainda pendente |

Referências internas: `docs/analysis_plan.md`, `docs/data_governance.md`,
`docs/data_service_eligibility.md` e `docs/paper_preparation.md`.
