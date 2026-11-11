# ADR 0027 — Interpretação conservadora de feixes secundários parciais

**Missão 7.0 — motor geométrico original.** Este incremento depende da
representação por nível da ADR 0026, já integrada na `main`.

## Evidência e algoritmo

Na pauta monofônica, a extração de hastes e feixe principal já exige
continuidade de tinta, direção comum, inclinação plausível, separação
mínima das notas e ausência de barras de compasso aceitas entre elas.

Agora, para cada par adjacente de hastes do **mesmo grupo principal**:

1. Uma faixa secundária com suporte >= 0,78 e lacuna limitada só é
   confirmada se a faixa intermediária apresentar pouca tinta
   (evitando um traço primário artificialmente espesso).
2. Suporte >= 0,55 ou faixa com conexão incerta torna o grupo
   inconclusivo. Traços fracos (suporte >= 0,18) impedem promover o
   restante de um grupo parcialmente confirmado.
3. Se todos os pares possuem conexão secundária, preserva-se o
   contrato legado de grupo homogêneo de semicolcheias.
4. Se apenas alguns pares possuem conexão secundária confirmada,
   as hastes diretamente conectadas recebem `sixteenth`, e as
   demais recebem `eighth`, **somente quando não existe marca
   secundária intermediária/ambígua entre os outros pares**.
5. Cada nota carrega `beam_levels` explícitos: nível 1 para todo
   o grupo e nível 2 apenas nos pares com tinta confirmada.
6. Um segundo feixe curto associado a uma nota isolada (*hook*) ainda
   exige uma classificação geométrica específica; o modelo MusicXML
   já suporta o valor, mas o algoritmo não o infere sem evidência.

As regras são heurísticas conservadoras e não provam que cada nota
proposta no corpus publicado esteja correta.

## Testes e avaliação

- Casos autorais independentes do reconhecedor: colcheia + duas
  semicolcheias e duas semicolcheias + colcheia com conexões parciais.
- Negativos: traço secundário quebrado, espessura mesclada, barras de
  compasso e marcas fracas em grupos com conexão secundária confirmada.
- O exportador conserva os dois níveis MusicXML com durações exatas;
  somente compassos rítmica e estruturalmente consistentes são
  exportados.
- Nenhum ground truth derivado de LilyPond divergente é utilizado
  para calcular percentuais de acerto.

## Limites e próximos passos

- Hooks isolados, alterações de direção de haste, múltiplas vozes e
  partituras degradadas precisam de diagnóstico e anotação adicionais.
- É possível que o método preserve mais casos inconclusivos no corpus
  real. Isso não deve ser tratado como falha sem avaliar o contexto.
- Repetir os testes em 150/200/300 DPI antes de reivindicar
  generalização; conferir regiões por músico e cotejar a edição
  publicada para estabelecer *precision* e *recall* reais.

Fonte de serialização: [MusicXML 4.0 Beam](
https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/beam/).
