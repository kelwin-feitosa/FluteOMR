# 0001 — Fundação Python local

Estado: adotada.

## Decisão

Usar Python >=3.12, layout `src/`, setuptools e ambiente virtual local. O ambiente
verificado oferece Python 3.12.3. Não há dependências de execução; pytest e Ruff
são ferramentas de desenvolvimento com versões fixadas no `pyproject.toml`.

## Alternativas e consequências

Python 3.10/3.11 ampliaria compatibilidade, mas exigiria validar versões adicionais
sem necessidade demonstrada no ambiente alvo. O CI começa com Python 3.12.
O layout `src/` exige instalar o pacote e evita que os testes importem por acidente
uma pasta na raiz em vez da distribuição instalada.

Setuptools atende ao pacote simples sem adicionar gerenciador de ambientes.
Poetry, uv e outros backends poderão ser avaliados quando houver necessidade.
As versões diretas são fixadas; o snapshot de dependências de desenvolvimento em
`requirements-dev.lock` também fixa as dependências transitivas e o backend.

Não selecionar GUI, bibliotecas de imagem/PDF, modelos de ML ou OMRs auxiliares
nesta etapa. Essa escolha mantém o núcleo leve e independente de interfaces no
Linux com i3-7100, 8 GB de RAM e sem GPU dedicada.
