# FluteOMR

Sistema original de reconhecimento óptico de partituras tradicionais impressas
para flauta transversal. O objetivo é receber PDFs e imagens e produzir MusicXML;
exportações MSCZ e PDF musical dependerão de integração apropriada.

## Estado atual e limites

O núcleo detecta pautas horizontais de cinco linhas em PNG/JPEG, agrupa sistemas
quando há evidência geométrica e oferece um detector experimental de clave de sol.
Há saída JSON e imagem de depuração. Não interpreta notas, ritmos ou outros
símbolos. Não há conversão PDF, exportação, interface gráfica ou modelos de ML.
O algoritmo é próprio; OMRs existentes não substituem o núcleo.

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
acesso ao PyPI; nenhum serviço externo participa do processamento. Pillow 12.3.0
é a única dependência de execução, para leitura e manipulação de imagens, sem
NumPy, OpenCV ou GPU. Para atualizar ferramentas, altere os pins no
`pyproject.toml`, regenere o lock em ambiente limpo e execute as verificações.

## Execução e qualidade

Valide a instalação e a geometria com os mesmos comandos executados pelo CI:

```bash
python -c "import fluteomr; print(fluteomr.__file__)"
python -m pytest -q
python -m ruff check .
python -m ruff format --check .
python -m pip check
```

Para aplicar formatação: `python -m ruff format .`. Os testes `tests/test_*.py`
verificam instalação e detecção contra posições sintéticas conhecidas. Ainda não
existe meta de cobertura ou métrica de reconhecimento de símbolos musicais.

## Demonstração local e API

Com o ambiente ativado, execute da raiz:

```bash
python -m tools.staff_examples --output outputs/staff-demo
python -m fluteomr outputs/staff-demo/symbols.png \
  --debug outputs/staff-demo/cli-debug.png > outputs/staff-demo/result.json
python -m fluteomr caminho/partitura.jpg
```

O gerador produz imagens próprias, anotações e `evaluation.json` com ground truth,
contagens, erros e tempos medidos. Escolha um diretório novo a cada avaliação;
saídas em `outputs/` são ignoradas. A CLI recebe um PNG/JPEG posicional e `--debug`
opcional; JSON vai para stdout, erros para stderr (código 2). Ausência/ambiguidade
são resultados normais (código 0). A saída de depuração não sobrescreve arquivos
existentes. Sua pasta de destino deve existir.

```python
from fluteomr import detect_staffs_file

result = detect_staffs_file("partitura.png")
print(result.status, result.staff_count)
for staff in result.staffs:
    print(staff.spacing, [line.y for line in staff.lines])
```

`detect_staffs(image)` aceita uma imagem Pillow sem mutá-la. `DetectionResult`
contém dimensões, `staffs`, `candidates`, `threshold` (limiar Otsu),
`analysis_threshold` (limiar efetivo usado) e diagnósticos; `to_dict()`
inclui `staff_count`. Cada pauta fornece cinco linhas ordenadas de cima para baixo,
espaçamento e `region`. Cada linha tem `x_start`, `x_end`, `y` (centro) e `thickness`.
Origem: canto superior esquerdo; x cresce à direita e y para baixo. Coordenadas
referem-se à imagem após orientação EXIF, com extremos de regiões inclusivos.
Transparência é composta sobre branco. O limite é 20 milhões de pixels.

Estados: `detected` aceita geometria; `no_staff` não encontra grupo válido;
`ambiguous` indica grupos concorrentes. Grupos ambíguos são omitidos de `staffs`,
mas suas linhas permanecem em `candidates`. Pautas independentes podem coexistir
com ambiguidade. Nenhum estado ou pontuação representa probabilidade de acerto.
`candidates` guarda os extremos brutos dos trechos mais longos; `staffs[*].lines`
guarda os extremos refinados, e `region` envolve esses extremos. A correção junta
evidências em uma faixa vertical estreita e trechos horizontais corroborados pelas
cinco linhas da própria pauta. Não usa os comprimentos de outras pautas da página.
Depuração: candidatos brutos laranja, linhas aceitas vermelhas, regiões azuis.
O diagnóstico `contrast_threshold_adjusted` indica um limiar mais claro que Otsu;
`contrast_retry` indica uma segunda tentativa após não encontrar grupos.

### Sistemas musicais (experimental)

`Staff` é a geometria de cinco linhas; `MusicSystem` agrupa pautas lidas na mesma
faixa da página. Execute `python -m fluteomr partitura.png --systems --debug
outputs/systems.png` para acrescentar `system_grouping` ao JSON e contornos
coloridos numerados à depuração. A saída legada sem `--systems` permanece igual.
Em Python, use `group_staffs(result.staffs)` após `detect_staffs(image)`. Cada
sistema contém `id` sequencial, `staff_indices` da detecção original, `staffs` e
`region`. O status `ambiguous` significa que a separação geométrica não é
justificável; pautas isoladas nesse caso são provisórias. A decisão e seus limites
estão em `docs/decisions/0004-system-grouping.md`.

### Partes instrumentais (modelo interno)

Uma `Part` é a sequência lógica associada a pautas de sistemas diferentes; não
equivale a uma pauta. `ScorePage` guarda sistemas e partes, e `StaffRef` mantém os
índices originais. Nenhum instrumento é inferido da imagem. Por exemplo:

```python
from fluteomr import group_staffs, propose_parts_by_order

grouping = group_staffs(result.staffs)
page = propose_parts_by_order(grouping)  # hipótese explícita, se não ambígua
```

`add_part(page, "Flauta transversal")` registra um instrumento informado pelo
usuário; `link_staff(page, part_id, system_id, staff_index)` cria ou corrige uma
ligação manual e `unlink_staff` a remove. Essas funções retornam nova página.
Sistemas de tamanhos diferentes ou agrupamento ambíguo não geram vínculos
automáticos. Decisão: `docs/decisions/0005-logical-parts.md`.

### Clave de sol (experimental)

`python -m fluteomr partitura.png --clefs --debug outputs/clefs.png` acrescenta
`clef_detection.observations` ao JSON e caixas verdes às claves aceitas. É
possível combinar `--clefs` e `--systems`. Em Python, use
`detect_treble_clefs(image, result)` após detectar as pautas. Cada observação
tem índice da pauta e status `detected`, `inconclusive` (mais de um componente
plausível) ou `no_treble` (nenhuma evidência que atenda às regras). `no_treble`
não comprova ausência de clave. Um resultado aceito traz tipo `treble`, caixa
inclusiva e evidências geométricas; não há confiança probabilística. O método
suprime linhas, procura componentes no início da pauta e verifica altura,
largura e expansão de curvas em relação ao espaçamento. Decisão:
`docs/decisions/0006-treble-clef-experiment.md`.

## Algoritmo, avaliação e limites

Escala de cinza e Otsu iniciam a máscara de pixels escuros. Para recuperar linhas
cinzentas, o limiar efetivo avança 30% da distância entre Otsu e o tom mais
frequente; se nenhum grupo aparecer, uma segunda tentativa usa um limiar próximo
ao fundo. O valor Otsu permanece em `threshold`. A projeção horizontal
seleciona faixas, cujos centros são ponderados pela quantidade de pixels escuros.
A validação usa comprimento, espessura, sobreposição horizontal e regularidade dos
quatro espaçamentos. Os parâmetros revisados estão em
`docs/decisions/0003-real-staff-robustness.md`.
Os limites horizontais refinados são usados antes de verificar a sobreposição:
isso permite agrupar linhas interrompidas em posições diferentes. Fragmentos
curtos e isolados não estendem uma pauta. As coordenadas x mantêm a origem e a
convenção de extremos inclusivos existentes.

### Avaliação local de imagens reais

O manifesto `tests/data/real_staff_counts.json` guarda apenas nomes e contagens,
sem imagens. Com os quatro arquivos presentes no diretório ignorado pelo Git:

```bash
python -m tools.evaluate_real_staffs --images-dir outputs/teste-real \
  --validate --debug-dir outputs/avaliacao-real-nova
```

O programa mostra contagem esperada, detectada e diferença por imagem e no total.
Em modo `--validate`, retorna 1 se houver diferença; arquivos ausentes são
informados e retornam 2 mesmo sem validação. Escolha uma nova pasta de depuração
para não sobrescrever saídas antigas. O CI normal usa apenas dados sintéticos.
O manifesto reflete a inspeção visual: 10 pautas em *Pirates*, 9 em *Quando*,
12 em *Mov. III* e 3 em *Twinkle*. As contagens inicialmente relatadas de 10
e 13 nas duas imagens centrais foram corrigidas após conferir os sistemas.
Igualdade de contagem não mede recall ou falsos positivos por posição; isso requer
anotações de referência das linhas em cada imagem.

Garantido pelos testes sintéticos: dez casos positivos (deslocamento, espessuras
1–4 px, espaçamentos 6–24 px, duas pautas, símbolos simples, interrupções curtas e
ruído de 0,5%) retornam a contagem correta, cinco linhas ordenadas e erro máximo
de centro <=2 px. Branco, quatro linhas e espaçamento inconsistente são rejeitados;
seis linhas igualmente espaçadas são ambíguas. PNG/JPEG, transparência, cinza,
extensões horizontais e CLI têm testes adicionais.

Limitações registradas em `evaluation.json`: cinco linhas não musicais com a mesma
geometria produzem falso positivo; rotação de 2° perde a pauta. Esses dois critérios
futuros têm testes `xfail(strict=True)`; use `python -m pytest -q -rx` para listar
suas razões. Não contam como acertos da avaliação principal. Inclinação, grandes
lacunas, pautas ocupando menos de 25% da largura, contraste não uniforme, fotografias,
manuscritos e pautas lado a lado não têm suporte garantido. Símbolos ou regras muito
longas podem dominar a projeção. Os testes sintéticos não demonstram precisão em
partituras reais. O detector de claves ainda precisa de caixas anotadas e fontes
variadas para avaliação rigorosa.

## Estrutura e contribuição

- `src/fluteomr/`: núcleo Python independente das futuras interfaces.
- `tests/`: testes reproduzíveis.
- `assets/`: recursos autorizados; leia suas regras antes de adicionar material.
- `tools/staff_examples.py`: geração sintética e avaliação reproduzível.
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
Novas alterações só serão verificadas remotamente após o push aprovado.

## Próxima etapa técnica

Anotar sistemas e caixas de claves em imagens autorizadas, testar fontes diversas
e usar conectores de sistema como evidência adicional. Depois avaliar correção de
pequenas inclinações. Conversão PDF e notas ficam para tarefas separadas.
