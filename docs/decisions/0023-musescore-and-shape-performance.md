# ADR 0023 — MuseScore como gerador de fixtures e matching de noteheads por prefixos

**11/11/2026 — implementação experimental — PR #6 (depende do PR #5).**

## Decisão implementada: otimização no motor Python próprio

A operação _shape da detecção de cabeças de notas somava individualmente pixels das máscaras elípticas em Python, milhões de vezes por página. A nova função _shape_from_prefix acumula contagens horizontais de tinta uma vez por linha, e consulta as mesmas máscaras em intervalos compactos. Não altera os critérios de classificação, coordenadas de busca, limiares musicais nem a dependência apenas de Pillow. A função antiga permanece para verificações A/B.

**Evidências reais** (partitura de Bach BWV 1013, primeira página, 200 DPI):

- [GitHub Actions](https://github.com/kelwin-feitosa/FluteOMR/actions/runs/43063272144): 29.325 coordenadas da pauta testadas no mesmo processo com zero divergências de forma e score.
- Tempo mediano da comparação por chamada em lote: algoritmo anterior 0,3706 s; novo 0,1099 s, **3,372 vezes mais rápido** na operação estudada.
- Construção do prefixo: 0,25758 s; memória extra estimada de 15.484.180 bytes para página inteira.
- Inferência completa com cProfile: 32,4654 s na nova execução, contra 162,5457 s na [execução anterior](https://github.com/kelwin-feitosa/FluteOMR/actions/runs/43019019074). São runners distintos: essa razão observacional de aproximadamente cinco vezes **não** é um experimento emparelhado controlado.
- As quantidades de 412 eventos propostos, 402 alturas inferidas, 72 durações inferidas e 39 diagnósticos permaneceram iguais.

Não há precisão de notas comprovada: faltam referências MusicXML independentes para a mesma edição.

## MuseScore Studio — fonte e aplicação prática

- [Repositório oficial](https://github.com/musescore/MuseScore), licença GPLv3.
- Em **src/notation/notationmodule.cpp**, os formatos mpos e spos são registrados como writers.
- Em **src/notation/internal/positionswriter.cpp**, grava-se XML com elementos de posições por compasso/segmento e associação a eventos. As posições dependem de escala de exportação; **não** são caixas de cabeças de notas nem anotação humana de partitura real.
- A exportação MusicXML ocorre em **src/importexport/musicxml/internal/export/exportmusicxml.cpp**.
- O [manual de linha de comando](https://handbook.musescore.org/pt_br/appendix/command-line-usage) documenta -o (exportação), -r (DPI), PDF, PNG, SVG, mpos e spos.

**Adotado:** ferramenta opcional tools.musescore_fixture. Recebe MusicXML de referência autoral, executa MuseScore instalado sem interface, cria PDF/PNG/mpos/spos, confere arquivos, SHA-256, versão e registra os resultados em manifesto de proveniência. O CI opcional utiliza o pacote MuseScore 3 do Ubuntu 24.04; a inspeção do código-fonte foi sobre o MuseScore Studio moderno. Diferenças entre as versões não devem ser pressupostas.

As gravuras dessa ferramenta têm status **source_authored**, nunca independentes ou revisadas por humanos automaticamente.

Exemplo:

    python -m tools.musescore_fixture tests/data/music_lab/dev_down_flags.musicxml --out-dir outputs/fixture-musescore --dpi 200 --format pdf --format png --format mpos --format spos

## Alternativas analisadas

| Sistema | Evidência de implementação | Uso adotado |
| --- | --- | --- |
| [Audiveris](https://github.com/Audiveris/audiveris) | README: morfologia para feixes, template matching para cabeças e redes para outras formas; arquivos app/src/main/java/org/audiveris/omr/sheet/beam/BeamsBuilder.java, sheet/rhythm/RhythmsStep.java | Estudo das relações símbolo–haste–feixe; futuro comparador separado, sem copiar código Java AGPLv3 |
| [homr](https://github.com/liebharc/homr) | README/pyproject.toml: modelo de OMR e exportação MusicXML, CPU via ONNX Runtime; AGPLv3 | Possível benchmark externo, não adicionar modelos grandes sem medir desempenho CPU/RAM |
| [MuseScore Studio](https://github.com/musescore/MuseScore) | Código C++, CLI documentada, formatos de exportação e posições | Gerador auxiliar de referências visuais, não motor de reconhecimento |
| [REA](https://github.com/morluto/rea) | Ferramenta MIT para engenharia reversa de executáveis | Não instalada: análise do código aberto é mais informativa para esta missão |

Os projetos GPL/AGPL podem ser estudados, mas **incorporação e redistribuição de código** exigiriam avaliar as obrigações de licença. Nenhum trecho de MuseScore, Audiveris ou homr foi incorporado ao motor Python.

## Prioridades resultantes

1. Continuar medindo o custo da matriz de prefixos em outras resoluções, especialmente no computador com 8 GB RAM; avaliar prefixos restritos a recortes de pauta.
2. Instrumentar os diagnósticos de duração para quantificar semicolcheias/feixes duplos e outros motivos de incerteza em partituras publicadas.
3. Obter referências MusicXML da mesma edição e revisadas por músicos antes de calcular acerto de nota/ritmo.
4. Explorar vínculos de feixes no Audiveris por abstração independente, sem copiar implementação incompatível.
