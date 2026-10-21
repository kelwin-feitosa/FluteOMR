# FluteOMR

Sistema original de reconhecimento óptico de partituras tradicionais impressas
para flauta transversal. O objetivo é receber PDFs e imagens e produzir MusicXML;
exportações MSCZ e PDF musical dependerão de integração apropriada.

## Estado atual e limites

O núcleo detecta pautas horizontais de cinco linhas em PNG/JPEG, agrupa sistemas
quando há evidência geométrica e oferece um detector experimental de clave de sol.
Uma CLI experimental infere semínimas/mínimas em um ou mais compassos controlados e exporta
MusicXML. Há saída JSON, depuração e interfaces locais de revisão. Ainda não há
conversão PDF, reconhecimento musical geral nem modelos de ML.
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
verificam instalação, detecção e métricas contra dados sintéticos conhecidos.
Ainda não existe meta de cobertura nem avaliação independente de símbolos reais.

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

### Referências anotadas e métricas (Fase 5.1)

O formato JSON versionado e os estados `present`, `absent` e `unknown` estão em
`docs/annotation-format.md`. Para gerar sugestões das quatro imagens locais,
sem convertê-las em referência:

```bash
python -m tools.evaluate_annotations suggest \
  --images-dir outputs/teste-real \
  --manifest tests/data/real_staff_counts.json \
  --output-dir outputs/fase5-1-suggestions
```

Use uma pasta de saída nova. Cada imagem gera `*.suggestions.json`,
`*.reference-draft.json` e `*.review.png` com IDs de pautas (`s0`...), sistemas
e claves. As contagens do manifesto aparecem apenas como informação preliminar.
Abra imagem e PNG lado a lado; corrija no rascunho regiões e cinco linhas,
ordem/pertencimento aos sistemas e estado de cada clave. Marque cada pauta
revisada `confirmed`, cada sistema conferido `confirmed`, e use `coverage: complete`
somente quando a respectiva lista for exaustiva. Uma clave não conferida fica
`unknown`, nunca `absent`. Defina `split: development` para essas quatro imagens,
pois já orientaram o desenvolvimento; reserve `test` para imagens independentes.

```bash
python -m tools.evaluate_annotations check \
  --annotation outputs/fase5-1-suggestions/IMAGEM.reference-draft.json \
  --images-dir outputs/teste-real
python -m tools.evaluate_annotations confirm \
  --annotation outputs/fase5-1-suggestions/IMAGEM.reference-draft.json \
  --images-dir outputs/teste-real \
  --output outputs/referencias-validadas/IMAGEM.reference.json \
  --reviewer SEU_IDENTIFICADOR --confirm-reviewed
python -m tools.evaluate_annotations evaluate \
  --annotations-dir outputs/referencias-validadas \
  --images-dir outputs/teste-real \
  --report outputs/relatorio-anotado.json \
  --errors-dir outputs/erros-anotados
```

Crie a pasta de referências antes de `confirm`; o comando não sobrescreve
arquivos. `check` valida estrutura, dimensões e SHA-256, mas não aprova o
conteúdo. `confirm` exige sua revisão explícita. `evaluate` usa apenas arquivos
`*.reference.json` validados; rascunhos não entram nas métricas. Sem referências
validadas, retorna `not_evaluable`. Saídas em `outputs/` são ignoradas pelo Git.
Os códigos de saída são 0 para execução válida (inclusive sem referência), 2
para formato/revisão inválidos, 3 para imagem/arquivo ausente e 4 para falha de
processamento. O relatório JSON separa `development` e `test` em `by_split`.

Precision = TP/(TP+FP), recall = TP/(TP+FN), e F1 é a média harmônica das duas.
Pautas usam pareamento espacial um-para-um; sistemas usam as pautas pareadas e
pares que devem ficar juntos; claves usam estados conhecidos e IoU da caixa
quando anotada. Relatórios mostram denominadores e `not_evaluable` quando a
referência é incompleta. Sem negativos conferidos, precision de claves não é
estimada. Tolerâncias e decisões estão em
`docs/decisions/0007-annotation-evaluation.md`. Resultados nas quatro imagens
locais são diagnósticos de desenvolvimento; uma avaliação de generalização exige
um conjunto `test` independente, anotado antes de ajustar detectores.

### Revisão visual de rascunhos (Fase 5.3)

O anotador local usa Tkinter + Pillow e mantém o formato 1 de
`docs/annotation-format.md`. Tkinter é opcional para os testes e o núcleo. No
Pop!_OS 24.04, o pacote do sistema é `python3-tk`; se `import tkinter` falhar,
instale-o pelo gerenciador de pacotes e recrie o `.venv` se necessário. A CLI
mostra um erro claro enquanto o módulo não estiver disponível. A interface não
executa os detectores nem transforma sugestões em referência validada.

Exemplo com o **rascunho de Fairy Tail** da Fase 5.2, se esses arquivos locais
estiverem presentes:

```bash
python -m tools.annotate \
  --annotation 'outputs/novas-partituras/suggestions/Fairy_Tail_Main_Theme_(flute_version)__c325b7598d_p001/Fairy_Tail_Main_Theme_(flute_version)__c325b7598d_p001.png.reference-draft.json' \
  --images-dir outputs/novas-partituras/png
```

Também é possível iniciar sem argumentos e usar **Abrir** para escolher o JSON e
a pasta da imagem. O modo **Revisar claves** mostra uma lista de pautas e foca
automaticamente a região inicial da clave selecionada. Use **Próxima pendente**
ou **Anterior** para percorrê-las. Uma sugestão aceita aparece tracejada;
**Confirmar sugestão** copia sua região apenas após o clique. Para uma pauta
inconclusiva como `s1`, escolha **Corrigir região / desenhar caixa**, arraste a
caixa sobre a clave, selecione o tipo visto e clique em **Confirmar correção
desenhada**. A caixa laranja tracejada é uma prévia: `Esc` a cancela sem editar
o rascunho. No mesmo modo, arraste uma caixa existente para movê-la ou sua alça
inferior direita para redimensioná-la, e confirme a correção. **Não consigo
identificar** conserva o estado desconhecido; **Não é clave de sol / outra
clave** distingue outra clave presente de ausência confirmada de qualquer clave.

Roda do mouse aproxima em torno do cursor; **Página**, **Largura** e
**Seleção** ajustam a vista. A ferramenta **Navegar** arrasta a página; as
barras fazem rolagem horizontal e vertical. As caixas e os estados só mudam
após ações explícitas de revisão. Use as caixas de seleção para ocultar pautas,
sistemas, claves ou sugestões. **Mostrar opções avançadas** abre edição
numérica, pauta/sistema, cobertura e checagem estrutural. A região de um sistema
deriva das pautas; edite seus IDs de membros para corrigir o agrupamento. O
painel lateral e as opções avançadas têm rolagem vertical. O
zoom nunca altera as coordenadas armazenadas.

Em Fairy Tail, a clave da pauta `s1` está `unknown` no rascunho; as caixas
(295,1362,374,1582) e (436,1404,518,1553) são hipóteses, não verdade. Revise
o PNG original antes de marcar `present` ou usar uma caixa. Para cada pauta,
confira também região, cinco linhas e estado `review_state`; para cada sistema,
confira `staff_ids` e seu estado. `unknown` significa não verificado;
`absent` significa **nenhuma clave visível**, não apenas ausência de sol. Se
houver outra clave presente, escolha `bass`, `alto` ou `other`. Use `complete`
somente após uma revisão exaustiva, e mantenha exemplos usados para ajustes em
`development`. O editor não escolhe automaticamente a partição nem uma clave.

**Salvar rascunho** grava de modo atômico; **Reverter** descarta alterações desde
o último salvamento, e trocar de arquivo ou fechar com mudanças pendentes pede
decisão. Referências `validated` abrem somente para leitura. **Checar** valida
formato, hash e dimensão, mas não comprova correção musical. A confirmação
definitiva continua separada na CLI existente, depois da revisão humana:

```bash
python -m tools.evaluate_annotations check \
  --annotation RASCUNHO.reference-draft.json --images-dir PASTA_DAS_IMAGENS
python -m tools.evaluate_annotations confirm \
  --annotation RASCUNHO.reference-draft.json --images-dir PASTA_DAS_IMAGENS \
  --output NOVA_REFERENCIA.reference.json --reviewer SEU_NOME --confirm-reviewed
```

`confirm` não sobrescreve um destino existente. O anotador não implementa
histórico complexo, escolha automática entre componentes inconclusivos, nem
anotação de notas ou ritmos. A abertura real da janela exige Tkinter e display;
as regras de edição têm testes headless.

### Editor OMR web local (Fase 5.4)

Inicie o servidor sem dependências web adicionais, a partir da raiz do projeto:

```bash
.venv/bin/python -m tools.web_editor
```

Abra **http://127.0.0.1:8765/** no navegador local. A tela inicial lista as
imagens já processadas em `outputs/novas-partituras/`, com contagens de pautas,
pendências de clave e correções salvas. Escolha `Fairy_Tail_Main_Theme_(flute_version)`
e clique em **Abrir no editor**. A página mostra sete pautas, seis claves de sol
aceitas pelo detector e `s1` pendente. **← Início** retorna ao catálogo; se
houver alterações não salvas, a interface pede confirmação antes de descartá-las.
Contagem zero de pendências não significa que a partitura foi validada.
Clique em uma pauta ou caixa para aproximá-la. O painel direito mostra recorte,
estado e diagnóstico. As caixas verdes são predições; a área âmbar tracejada de
`s1` é apenas uma zona aproximada para revisão, **não** uma caixa detectada.

Para corrigir `s1`, clique em **Desenhar região**, arraste sobre a clave que você
identificou no PNG, escolha seu tipo e use **Aplicar correção**. Para corrigir
uma predição aceita, selecione-a, escolha outro tipo ou desenhe outra caixa e
aplique. **Confirmar ausência de qualquer clave** só deve ser usado quando não
houver nenhuma clave na pauta; ausência de sol não basta. Use **Salvar
correções** para persistir e reabra a página para conferir. `Esc` cancela o
desenho. **Largura**, **Página**, `+`/`−`, `Ctrl`+roda do mouse, filtros e botões
de recolher os painéis ajudam na navegação. Encerre o servidor com `Ctrl+C`.
As caixas são apenas contornos, inclusive ao passar o mouse; no modo de desenho
elas não interceptam o arraste sobre a partitura.

O servidor lê sugestões e PNGs, mas grava somente arquivos versionados de
correção operacional em `outputs/web-editor/corrections/`, ignorados pelo Git.
Eles registram decisões explícitas e hashes das fontes; predições não corrigidas
continuam automáticas. Isso **não** produz ground truth nem valida referências
da Fase 5.1. A API permite apenas arquivos do catálogo local e exige token e
origem local para escrita. Diretórios alternativos podem ser configurados com
`--images-dir`, `--suggestions-dir`, `--corrections-dir` e `--port` ao iniciar.
Detalhes e limites estão em `docs/decisions/0009-local-web-review.md`. Não há
importação de PDF, reconhecimento de notas ou modo de edição musical nesta fase.

### Transcrição musical experimental (Sprint 1A)

O primeiro caminho óptico, separado da CLI legada e dos editores, lê **uma pauta
horizontal e um compasso** em PNG limpo. Gere exercícios originais e suas
referências somente para comparação posterior:

```bash
.venv/bin/python -m tools.music_examples --output-dir outputs/sprint-1a/corpus
.venv/bin/python -m tools.transcribe \
  outputs/sprint-1a/corpus/dev_lines_spaces.png \
  --clef treble --time 4/4 --measure-left 110 --measure-right 410 \
  --output outputs/sprint-1a/minha-transcricao.musicxml
.venv/bin/python -m tools.evaluate_music_examples \
  --corpus-dir outputs/sprint-1a/corpus
```

O comando imprime o modelo e problemas em JSON; se uma altura/duração for
inconclusiva ou a soma não fechar quatro tempos, termina com erro e **não** grava
MusicXML. Escolha um caminho novo para cada saída: a CLI não sobrescreve arquivos.
`--clef treble`, `--time 4/4` e os limites horizontais são **configuração do
usuário**, não reconhecimento visual. A sequência, as alturas e as figuras
semínima/mínima vêm dos pixels. O detector remove linhas da pauta preservando
tinta com continuidade vertical, procura cabeças preenchidas/vazadas em posições
diatônicas, exige haste e ordena as notas por `x`. O modelo guarda região de
origem e a proveniência dos dados; o XML é serializado com a biblioteca padrão.
Sua estrutura `score-partwise` segue o [exemplo mínimo MusicXML 4.0 do W3C](https://www.w3.org/2021/06/musicxml40/tutorial/hello-world/).
O avaliador abre cada referência **depois** da inferência e pareia cabeças por
posição horizontal em até 0,75 do espaçamento anotado; os exercícios `test` têm
conteúdo reservado, mas usam a mesma família de desenho programático.

O modo original de um compasso não detecta barras. O modo opt-in da Sprint 1B
detecta barras internas em pautas horizontais limpas. Fórmula, clave, acidentes,
pausas, ligaduras e vozes seguem sem reconhecimento visual nesta etapa. Colcheias
simples foram acrescentadas experimentalmente na Sprint 1C-B. Uma nota
omitida pode escapar da checagem se as durações restantes ainda somarem 4/4.
Resultados sintéticos não medem
precisão em partituras reais; fontes, gravações e layouts independentes precisam
de referência humana. MuseScore não estava disponível na implementação, então
o XML foi verificado por parsing estrutural, sem teste de abertura no aplicativo.

### Dois compassos e diagnóstico (Sprint 1B)

Com uma **única pauta** e os limites externos informados, `--auto-bars` procura
traços verticais contínuos entre a primeira e a quinta linha e rejeita colunas
próximas de cabeças como possíveis hastes. Os limites externos continuam sendo
configuração; barras internas, cabeças, alturas e semínimas/mínimas vêm da imagem.
O JSON acrescenta `symbol_diagnostics` com barras aceitas/rejeitadas e vínculos
de haste. Cada nota tem `candidate_id` e `source_page`; cada compasso tem região,
IDs das barras e proveniência de cada limite. A opção `--debug` grava pauta em
azul, cabeças em verde/laranja e barras aceitas/rejeitadas em roxo/vermelho.

```bash
.venv/bin/python -m tools.transcribe imagem-de-uma-pauta.png \
  --clef treble --time 4/4 --measure-left 100 --measure-right 700 \
  --auto-bars --debug outputs/sprint-1b/diagnostico.png \
  --output outputs/sprint-1b/transcricao.musicxml
```

Para reproduzir a inspeção externa local, se a imagem de Twinkle da Fase 2
estiver disponível em `outputs/teste-real/`, isole e amplie os dois primeiros
compassos sem tocar no original:

```bash
mkdir -p outputs/sprint-1b
.venv/bin/python -c "from PIL import Image; im=Image.open('outputs/teste-real/Twinkle_Twinkle_Sheet_Music.png'); im.crop((75,57,522,145)).resize((894,176)).save('outputs/sprint-1b/twinkle-2x.png')"
.venv/bin/python -m tools.transcribe outputs/sprint-1b/twinkle-2x.png \
  --clef treble --time 4/4 --measure-left 125 --measure-right 880 \
  --auto-bars --debug outputs/sprint-1b/twinkle-debug.png \
  --output outputs/sprint-1b/twinkle.musicxml
```

Essa inspeção visual produziu `C4 C4 G4 G4 | A4 A4 G4` (a última é mínima),
mas **não** é uma métrica de precisão: a partitura externa não possui referência
musical humana validada. As medidas reais permanecem em `outputs/`, ignorado pelo
Git. Barras duplas/finais, pautas pequenas sem ampliação e símbolos complexos
seguem experimentais. A soma rítmica correta não prova ausência de notas perdidas.
Detalhes da decisão estão em `docs/decisions/0011-symbol-relations-and-barlines.md`.

### Laboratório de avaliação musical (Sprint 1C-A)

O avaliador compara eventos previstos com uma referência MusicXML escrita
separadamente; não lê essa referência durante a inferência. Gere o corpus
original e execute o caso de desenvolvimento versionado:

```bash
.venv/bin/python -m tools.music_examples --output-dir outputs/sprint-1a/corpus
.venv/bin/python -m tools.evaluate_music \
  --manifest tests/data/music_lab/manifest.json \
  --images-dir outputs/sprint-1a/corpus \
  --report outputs/sprint-1c-a/report.json
```

O manifesto versão 1 associa ID, nome da imagem, MusicXML de referência, origem,
`development`/`validation`/`test`, estado `source_authored`/`draft`/`validated` e os limites
configurados do compasso. `draft` é transcrito, mas retorna `not_evaluated`; só
marque `validated` após revisão humana real. O exemplo versionado é sintético e
`development`, não demonstra generalização. Mantenha imagens externas em
`outputs/` e nunca use o conjunto `test` para ajustar limiares.

O alinhamento usa números explícitos de compasso; dentro de cada compasso,
emprega custo unitário para inserir, omitir ou substituir notas, preferindo
substituição em empates. Partes ainda são pareadas pela ordem. Durações são comparadas como frações
de semínima via `divisions` do MusicXML. O relatório separa erros de altura,
oitava e duração, além de compassos extras/ausentes. `matches` exige altura,
oitava e duração juntas; `pitch_correct_aligned` e `duration_correct_aligned`
usam apenas pares alinhados. `duration_coverage` indica quantos eventos previstos
têm duração. Um compasso com símbolo sem suporte ou nota inconclusiva fica sem
pontuação: `skipped_reference_events` e `skipped_predicted_events` mostram a
cobertura perdida, e `full_match_fraction` vira `not_evaluated`. Pausas, alterações
cromáticas, acordes e ornamentos ficam `unsupported`; a notação gráfica é
`not_evaluated`. `xml_export=well_formed_not_schema_validated` verifica apenas
parsing XML, não compatibilidade completa com MuseScore. O fluxo de anotação
geométrica das Fases 5.1–5.4 permanece separado desta referência musical.
Veja `docs/decisions/0012-music-evaluation-lab.md`.

MuseScore Studio 4.7.4, já disponível como Flatpak de usuário, foi testado
opcionalmente com a referência original: `flatpak run org.musescore.MuseScore`.
As exportações PNG, PDF, MSCZ, `mpos`, `spos` e `--score-elements` funcionaram.
`mpos` fornece região do compasso e `spos` regiões de segmentos na altura da
pauta, não caixas individuais de cabeças. Em 300 DPI, as coordenadas foram
alinhadas ao PNG dividindo por 48; a escala precisa ser verificada para cada
DPI e versão. Os arquivos experimentais ficam em `outputs/musescore-1c-a/`.
Essa ferramenta permanece externa e opcional; consulte a decisão 0013.

### Colcheias experimentais (Sprint 1C-B)

O pipeline reconhece bandeirolas simples e feixes simples ligados a hastes de
cabeças preenchidas. A duração é `1/2` semínima; feixes aceitos aparecem como
`begin`/`continue`/`end` no MusicXML. Feixe duplo detectado fica inconclusivo e
bloqueia a exportação. O JSON do modo `--auto-bars` inclui `rhythm_evidence` em
`symbol_diagnostics`. Clave, fórmula e limites externos continuam configurados.

Para repetir a avaliação local, renderize as quatro referências próprias com o
MuseScore Flatpak 4.7.4, se disponível, e recorte somente a primeira pauta. O
recorte é preparação manual documentada, não uma detecção automática:

```bash
mkdir -p outputs/sprint-1c-b
for name in dev_eighth_flags dev_eighth_pair dev_eighth_beams holdout_eighth_mix; do
  flatpak run --env=QT_QPA_PLATFORM=offscreen org.musescore.MuseScore \
    -r 300 -o "outputs/sprint-1c-b/$name.png" "tests/data/music_lab/$name.musicxml"
done
.venv/bin/python -c "from PIL import Image; from pathlib import Path; p=Path('outputs/sprint-1c-b'); names=('dev_eighth_flags','dev_eighth_pair','dev_eighth_beams','holdout_eighth_mix'); [(lambda n: Image.open(p/f'{n}-1.png').crop((250,475,2300 if n=='holdout_eighth_mix' else 850,700)).save(p/f'{n}-staff.png'))(n) for n in names]"
.venv/bin/python -m tools.evaluate_music \
  --manifest tests/data/music_lab/eighth_manifest.json \
  --images-dir outputs/sprint-1c-b
```

O manifesto usa limite esquerdo 200; limite direito 520 nos três recortes de
600 px e 2020 no recorte largo. Na Sprint 1C-B, a sequência de desenvolvimento
teve 13/13 eventos correspondentes; o antigo caso reservado teve 3/6, com três
durações erradas. Como ele já foi consultado, agora é `validation`, não teste
cego. Os resultados são de partituras **originais renderizadas pelo mesmo
programa**, não de partituras reais independentes. A abertura e o round-trip de
um MusicXML com quatro colcheias preservaram eventos e marcadores de feixe no
MuseScore. Veja as decisões 0014 e 0015. Não use o conjunto `test` para ajustar limiares.

### Robustez rítmica e página inteira (Sprint 1C-B.2)

Bandeirolas são avaliadas dos dois lados da haste descendente pela extensão e
progressão da curva. Evidência fraca deixa a duração inconclusiva com diagnóstico
`weak_flag_geometry` e bloqueia MusicXML. Feixes exigem tinta contínua entre
pontas de hastes, sem limite máximo de distância entre cabeças; lacunas longas
e barras aceitas impedem a relação. Cabeças vazadas exigem tinta nas duas
laterais do contorno, preservando mínimas legítimas próximas de outras notas.
Uma segunda passagem de projeção encontra pautas estreitas em páginas com
margens largas, mantendo coordenadas originais.

Para renderizar os exercícios próprios a 300 DPI e transcrever uma página
completa sem recorte manual:

```bash
mkdir -p outputs/sprint-1c-b2
for name in dev_down_flags dev_long_beam; do
  flatpak run --env=QT_QPA_PLATFORM=offscreen org.musescore.MuseScore \
    -r 300 -o "outputs/sprint-1c-b2/$name.png" "tests/data/music_lab/$name.musicxml"
done
.venv/bin/python -m tools.transcribe outputs/sprint-1c-b2/dev_down_flags-1.png \
  --clef treble --time 4/4 --measure-left 450 --measure-right 770 \
  --output outputs/sprint-1c-b2/dev_down_flags-predicted.musicxml
```

O avaliador usa recortes de 600×225 para os dois novos casos de desenvolvimento:

```bash
.venv/bin/python -c "from PIL import Image; from pathlib import Path; p=Path('outputs/sprint-1c-b2'); [(lambda n: Image.open(p/f'{n}-1.png').crop((250,475,850,700)).save(p/f'{n}-staff.png'))(n) for n in ('dev_down_flags','dev_long_beam')]"
.venv/bin/python -m tools.evaluate_music \
  --manifest tests/data/music_lab/eighth_robustness_manifest.json \
  --images-dir outputs/sprint-1c-b2
```

`dev_down_flags` passou de 2/4 para 4/4 eventos completos; `dev_long_beam`
manteve 5/5. A validação previamente consultada passou de 3/6 para 6/6. Dois
novos exercícios de teste foram renderizados e avaliados uma vez após congelar
o código, com 9/9 correspondências, **todos no mesmo renderizador MuseScore**.
Isso não mede precisão em partituras reais nem generalização entre fontes.
As imagens e os relatórios permanecem em `outputs/`. O teste reservado já foi
aberto: uma futura avaliação cega exige novos exemplos.
A falha histórica de 200 DPI foi investigada na retomada descrita abaixo;
ela não demonstrava rearranjo horizontal pelo MuseScore.

Para reproduzir esse resultado conhecido (não como novo teste cego), renderize
`blind_down_flags` e `blind_long_beam` com o mesmo comando MuseScore acima e
execute:

```bash
.venv/bin/python -m tools.evaluate_music \
  --manifest tests/data/music_lab/eighth_blind_manifest.json \
  --images-dir outputs/sprint-1c-b2
flatpak run --env=QT_QPA_PLATFORM=offscreen org.musescore.MuseScore \
  -o outputs/sprint-1c-b2/blind_long_beam-predicted.mscz \
  outputs/sprint-1c-b2/blind_long_beam-predicted.musicxml
```

O segundo comando exige antes um MusicXML previsto gerado por
`tools.transcribe`; a reexportação do MSCZ permite comparar eventos e
marcadores `<beam>` em vez de comparar texto XML bruto.

### Retomada: amostragem de cabeças em 200 DPI

A remoção de pauta agora respeita sua espessura inclusiva no raster. Sondas
concorrentes da mesma cabeça priorizam uma haste observada, preservando a
pontuação geométrica original. Cabeças vazadas exigem uma cavidade fechada
antes da supressão das linhas, para não confundir feixe e pauta com mínima.

Na transcrição, pautas com espaçamento abaixo de 16 px usam uma ampliação
**local** bilinear para 20 px/espaço para recuperar cabeças vazadas ausentes.
Candidatos nativos válidos são preservados; cada cabeça recuperada precisa de
cavidade e haste também na imagem original. As coordenadas voltam à imagem
original; hastes e ritmo continuam examinando os pixels originais.
`detect_noteheads(..., normalize=True)` oferece essa opção na API geométrica;
`normalize_heads=False` ou `--native-heads` mantêm o caminho nativo para comparação.
Não há escolha de escala baseada na referência ou no fechamento do compasso.

Exercícios próprios rasterizados estão em `tests/data/music_lab/raster/`, com
proveniência e hashes. São dados de **desenvolvimento**, não teste independente:

```bash
.venv/bin/python -m tools.evaluate_music \
  --manifest tests/data/music_lab/resolution_manifest.json \
  --images-dir tests/data/music_lab/raster
.venv/bin/python -m tools.transcribe \
  tests/data/music_lab/raster/dev_down_flags-200.png \
  --clef treble --time 4/4 --measure-left 20 --measure-right 233 \
  --instrument flute --output outputs/recognized-flute-200.musicxml
```

O caso `dev_down_flags` passou de três candidatos, dois inconclusivos, para
4/4 eventos completos em 200 DPI, mantendo 4/4 em 300 DPI. O mesmo resultado
foi conferido nas páginas integrais. Os casos antigos de desenvolvimento
mantiveram 13/13 eventos e a validação previamente consultada, 6/6.
A substituição integral dos candidatos por versões ampliadas piorou um feixe
reduzido a 2/3 da escala. A recuperação seletiva corrigiu essa regressão: o
exemplo tem 5/5 eventos nessa escala e em 80%. Isso ainda não demonstra suporte
geral a 200 DPI, outras fontes ou imagens degradadas. Não há nova métrica de
acurácia em partitura real sem referência humana validada.

`--instrument flute` informa explicitamente flauta transversal em Dó ao MusicXML
(programa MIDI MusicXML 74), sem transposição ou restrição de tessitura. O nome
da parte não determina o instrumento. Feixes inconsistentes bloqueiam a saída.
O avaliador também marca reposicionamento temporal (`backup`/`forward`),
múltiplas vozes/pautas e ligaduras como `unsupported`, em vez de contá-los como
acertos. Parsing XML, validação por esquema e equivalência musical permanecem
verificações distintas. Consulte a decisão 0016.

### Sprint 1D: avaliação por obra, variante e compasso

O laboratório aceita `configured.auto_bars: true` para múltiplos compassos e
`reference_status: "missing"` com `reference: null` para materiais sem referência
humana. Esses materiais são processados, mas ficam `not_evaluated`. Rascunhos
continuam sem pontuação. `--continue-on-error` registra imagens com falha e
retorna código 1 ao final; erros de formato continuam retornando 2.

`--summary` inclui eventos e compassos conhecidos inclusive nas falhas, além
dos eventos não avaliados. `measure_results` detalha cada compasso e
`measure_metrics` separa correto, incorreto e não avaliável. O total é a união
dos compassos de referência e previstos, portanto inclui compassos extras.
O pareamento usa número explícito: uma barra falsa pode causar simultaneamente
inserções e omissões de eventos. A fração agregada conta correspondências
confirmadas sobre **todos** os eventos conhecidos; com eventos não avaliados,
é um limite inferior observado, não uma estimativa de acurácia geral.

`work_id` identifica a obra; fonte e DPI são variantes, não obras independentes.
`--split development` ou `--split validation` evita abrir o conjunto reservado.
Sem esse filtro, o comportamento anterior de processar todo o manifesto permanece.

Três exercícios próprios novos em `tests/data/music_lab/sprint1d/` têm referência
MusicXML independente da inferência: dois de desenvolvimento e um de validação,
avaliado após congelar o detector. Os símbolos e durações vêm dos pixels; clave,
4/4 e limites externos são configuração. Clave/fórmula estão visualmente ocultas
nesses exercícios, que não reproduzem a complexidade de uma partitura real.
Leland e Bravura são fontes do **mesmo MuseScore**, não renderizadores independentes.

Para renderizar com o Flatpak existente e avaliar:

```bash
mkdir -p outputs/sprint-1d/rendered
for name in dev_register dev_beams validation_intervals; do
  for font in Leland Bravura; do
    for dpi in 150 200 300; do
      flatpak run --env=QT_QPA_PLATFORM=offscreen org.musescore.MuseScore \
        -S "tests/data/music_lab/sprint1d/styles/$font.mss" -r "$dpi" -T 12 \
        -o "outputs/sprint-1d/rendered/$name-$font-$dpi.png" \
        "tests/data/music_lab/sprint1d/$name.musicxml"
    done
  done
done
.venv/bin/python -m tools.evaluate_music \
  --manifest tests/data/music_lab/sprint1d/development-manifest.json \
  --images-dir outputs/sprint-1d/rendered --split development \
  --continue-on-error --summary --report outputs/sprint-1d/development-report.json
```

Troque por `validation-manifest.json` e `--split validation` para a validação já
consultada. Limites e imagens foram registrados para MuseScore 4.7.5 com corte
de 12 px; outra versão/layout exige conferir a configuração, não alterar a referência.

As correções exigem suporte horizontal compacto para cabeças preenchidas e
calculam alturas entre as linhas locais observadas. No desenvolvimento a 150
DPI, correspondências completas passaram de 8/30 para 23/30 e candidatos de
57 para 25; a validação nova permaneceu em 4/14, com barras falsas e omissões.
Em 200/300 DPI, a versão final obteve 30/30 no desenvolvimento e 14/14 na
validação, em cada resolução. São 132 instâncias renderizadas de 22 eventos
musicais em três exercícios; não 132 notas independentes nem precisão em
partituras reais. Detalhes, limitações e protocolo estão na decisão 0017.

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
lacunas, contraste não uniforme, fotografias,
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

Avaliar transcrições contra trechos reais de flauta com referências musicais
revisadas por humanos e renderização independente. Depois, estabilizar ritmo
em fontes variadas antes de ampliar para pausas e acidentes.
