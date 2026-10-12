# 0010 — Primeiro compasso óptico até MusicXML

Estado: experimental.

## Decisão

Manter a CLI existente e oferecer `tools.transcribe` para um PNG com uma pauta.
Clave de sol, 4/4 e limites do único compasso são parâmetros explícitos. O motor
infere cabeças, alturas e figuras a partir da imagem; a referência musical não
participa da inferência. `MusicScore`, `MusicPart`, `Measure` e `Note` são
separados das estruturas geométricas de `score.py`, preservando a possibilidade
de vários compassos e pautas por parte sem implementá-los agora.

Após binarizar com o limiar da detecção de pauta, linhas horizontais são
suprimidas apenas onde não há suporte vertical. Máscaras elípticas relativas ao
espaçamento avaliam núcleo e anel da cabeça; tinta vertical próxima à borda
indica haste. A posição em meios espaçamentos a partir da linha inferior (Mi4)
define a altura diatônica. Cabeça preenchida com haste vira semínima; vazada com
haste vira mínima. Ausência de haste produz duração inconclusiva. Scores com
incerteza essencial ou soma rítmica divergente não são exportados como XML final.

MusicXML 4.0 é serializado via `xml.etree.ElementTree`, evitando `music21` e
dependências extras para esse subconjunto. Não há chave/alteração presumida.

## Evidência e limites

Exercícios originais Pillow fornecem desenvolvimento e reserva por conteúdo e
escala. A referência é lida apenas depois de transcrever; pareamento espacial
um-para-um permite contar cabeças ausentes e extras. A reserva ainda compartilha
o estilo de desenho com o desenvolvimento e não é teste de generalização para
fontes de gravação ou partituras reais. MuseScore não estava instalado no ambiente,
portanto a abertura do XML por ele permanece sem verificação.

O scanner é proporcional à largura do compasso, ao espaçamento da pauta e às
posições diatônicas consideradas. Não interpreta cifras, acidentes, pausas,
barras, notas ligadas, múltiplas vozes ou múltiplos sistemas. Se uma omissão ainda
deixar quatro tempos inferidos, a checagem de soma não a detecta; a avaliação
independente precisa cobrir esse caso. Um próximo incremento deve testar fontes
e partituras autorizadas com anotação humana, além de localizar compassos.
