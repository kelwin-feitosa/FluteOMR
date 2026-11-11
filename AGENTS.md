# Repository Guidelines

## Objetivo e escopo inicial

FluteOMR é um OMR original para partituras tradicionais impressas de flauta transversal. Receberá PDFs e imagens para reconhecer progressivamente a estrutura musical e produzir MusicXML; MSCZ e PDF musical dependerão de integração apropriada.

Desenvolva o motor de reconhecimento no próprio projeto. Audiveris, HOMR e outros OMRs podem servir como referências, comparações ou auxiliares, nunca substituir o núcleo. Priorize partituras limpas, digitalmente geradas, com uma pauta em clave de sol. Não trate notas incomuns para flauta como erros automaticamente; sinalize incertezas.

## Estrutura e arquitetura

O núcleo está em `src/fluteomr/`, os testes em `tests/` e as regras para recursos em `assets/`. `pyproject.toml` configura o projeto; `README.md` documenta instalação e verificações. Registre decisões em `docs/decisions/`. Há detecção de pautas em imagens PNG/JPEG e páginas PDF rasterizadas opcionalmente, sistemas, clave de sol experimental e um pipeline limitado de notas até MusicXML. `tools/staff_examples.py` gera exemplos próprios e avaliação.

Use Python no processamento, com núcleo independente das interfaces e compartilhável futuramente entre desktop e navegador. Não escolha framework gráfico antecipadamente sem justificativa. Registre decisões arquiteturais relevantes, alternativas e consequências. Considere Linux, Intel i3-7100, 8 GB de RAM e ausência de GPU dedicada; justifique dependências pesadas.

## Desenvolvimento e estilo

Use Python >=3.12 e o ambiente `.venv/`. Instale as ferramentas com `python -m pip install -r requirements-dev.lock` e o pacote com `python -m pip install --no-build-isolation --no-deps -e .`. Use quatro espaços, nomes descritivos e Ruff, sem misturar reformatação com mudanças funcionais. Mantenha comandos e versões documentados no `README.md`.

Trabalhe em tarefas pequenas, com critérios de aceitação explícitos. A meta inicial é entrada PDF/imagem, detecção das cinco linhas e localização de cabeças de notas em exemplos controlados. A etapa atual cobre cabeças de notas e figuras simples em exercícios controlados; a seleção e rasterização de páginas PDF são experimentais, mas o reconhecimento musical geral e a montagem automática de múltiplas páginas continuam futuros.

## Testes e precisão

Priorize precisão verificável: testes reproduzíveis, métricas, visualizações de depuração e registro de casos de falha. Use `python -m pytest -q`, `python -m ruff check .` e `python -m ruff format --check .`; o CI repete essas verificações. Ainda não há limiar de cobertura. Mantenha fixtures pequenas e nomes descritivos. Relate resultados reais; nunca declare aprovação sem execução.

## Alterações, commits e revisão

Preserve alterações existentes. Sem autorização, não apague arquivos, execute comandos destrutivos, altere configurações globais ou faça commits e pushes. Use `git status --short`, `git diff --check` e `git diff --cached` para revisão; arquivos não rastreados exigem inspeção própria.

Sem histórico, não há convenção de commits estabelecida; prefira assuntos imperativos e mudanças focadas. PRs devem explicar alterações, validação, issues relacionadas e mudanças de configuração; inclua imagens para alterações visuais.

## Fluxo de PRs e merges autorizado

O mantenedor autorizou explicitamente o agente a realizar commits,
criar PRs e **integrar na `main` sem nova aprovação para cada mudança**
quando todas as exigências forem cumpridas: testes existentes e novos,
lint, formatação, segurança, licenças, compatibilidade e CI concluídos
com sucesso no SHA exato do PR, sem conflitos nem regressões não
justificadas. Um CI verde não prova precisão musical em corpus real:
registre a classificação da referência e as limitações da evidência.

Mantenha cada alteração em branch criada da `main`, sem cadeias de PRs
dependentes. Após o merge, confirme a versão e, quando aplicável, os
checks da `main`. O workflow de limpeza pode excluir a branch de PR
**somente depois que o GitHub confirmar o merge**, nunca antes.
Não force push na `main`, não contorne branch protection, não oculte
falhas e não faça merge quando os critérios não forem satisfeitos.
Em caso de bloqueio, mantenha o trabalho revisável e documente o motivo.

## Segurança, custos e materiais

Não introduza serviços pagos, APIs com cobrança ou dependências de nuvem sem aprovação. Não inclua partituras de terceiros sem verificar condições de uso e distribuição. Não versione credenciais ou configurações privadas; use exemplos com placeholders e ignore arquivos locais e saídas geradas em `.gitignore`.
