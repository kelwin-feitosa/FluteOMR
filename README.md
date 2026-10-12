# FluteOMR

Sistema original de reconhecimento óptico de partituras tradicionais impressas
para flauta transversal. O objetivo é receber PDFs e imagens e produzir MusicXML;
exportações MSCZ e PDF musical dependerão de integração apropriada.

## Estado atual e limites

Esta etapa oferece apenas a fundação Python, instalação, testes e CI. Ainda não há
leitura de partituras, detecção de pautas/notas, exportação, interface ou modelos de
ML. O motor será próprio; OMRs existentes não substituirão o núcleo.

O alvo inicial são partituras limpas, digitalmente geradas, com uma pauta em clave
de sol. Notas incomuns para flauta não devem ser descartadas automaticamente.

## Instalação local

Requisitos: Python >=3.12 e suporte a `venv`. Ambiente validado: Linux, Python
3.12.3; planejamento para Intel i3-7100, 8 GB de RAM, sem GPU dedicada.

Na raiz do projeto:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.lock
python -m pip install --no-build-isolation --no-deps -e .
```

O lock fixa ferramentas, backend e dependências transitivas. A instalação requer
acesso ao PyPI; nenhum serviço externo participa do processamento. O núcleo não
tem dependências de execução. Para atualizar ferramentas, altere os pins no
`pyproject.toml`, regenere o lock em ambiente limpo e execute as verificações.

## Execução e qualidade

Não há aplicativo ou CLI de reconhecimento nesta etapa. Valide a instalação:

```bash
python -c "import fluteomr; print(fluteomr.__file__)"
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m pip check
```

Para aplicar formatação: `python -m ruff format .`. Os testes `tests/test_*.py`
verificam importação e metadados da distribuição instalada, sem alterar `sys.path`.
Ainda não existe meta de cobertura ou métrica de precisão musical.

## Estrutura e contribuição

- `src/fluteomr/`: núcleo Python independente das futuras interfaces.
- `tests/`: testes reproduzíveis.
- `assets/`: recursos autorizados; leia suas regras antes de adicionar material.
- `docs/decisions/`: decisões, alternativas e consequências arquiteturais.
- `.github/workflows/ci.yml`: testes, lint, formatação e dependências em Python 3.12.
- `AGENTS.md`: orientações obrigatórias para contribuições.

Use quatro espaços, nomes descritivos e tarefas pequenas com critérios de
aceitação. Preserve trabalho existente e execute os testes pertinentes. Não faça
commits ou pushes sem aprovação. Partituras privadas devem ficar em `private/` ou
`assets/private/`; saídas em `outputs/` ou `results/`, todos ignorados pelo Git.
Não inclua credenciais, materiais sem autorização ou serviços pagos.

O workflow usa GitHub Actions sem deploy ou publicação. Em repositório privado,
consome a franquia de minutos do plano; mantenha cobrança adicional desativada.
Sua execução remota só poderá ser confirmada após o push aprovado.

## Próxima etapa técnica

Definir uma tarefa pequena para entrada e processamento de uma imagem sintética
autorizada, com resultado esperado e teste reproduzível. Em seguida, avaliar
entrada PDF e rasterização local, consumo de memória e visualizações de depuração,
antes da detecção das cinco linhas da pauta e das cabeças de notas.
