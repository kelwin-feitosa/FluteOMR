# ADR 0024 — Semicolcheias apenas em grupos de feixes duplos completos

**Status:** implementação experimental; validação em desenvolvimento, 11/11/2026.
**Escopo:** flauta solo, pauta horizontal impressa, cabeças preenchidas com
hastes ligadas; sem feixes secundários parciais, quiálteras ou pausas.

## Motivação

Na página 1 da Partita BWV 1013 (Mutopia, 200 DPI), o motor anterior
propunha 412 eventos e 402 alturas, mas determinava apenas **72 durações**.
As outras **340** eram inconclusivas: 319 com diagnóstico de feixe duplo e
21 com haste não confirmada. A indicação de feixe duplo era propagada a
todos os membros de grupos conectados, mesmo quando a segunda linha
era visível apenas entre alguns pares.

## Contrato introduzido

- `Duration("sixteenth")` representa **Fraction(1, 4)** de semínima.
- O exportador escreve `<divisions>4</divisions>` quando necessário,
  `<type>16th</type>` e `<beam number="1">` e
  `<beam number="2">`, com begin/continue/end para o **grupo homogêneo**.
  Essa estrutura segue o [MusicXML 4.0 oficial](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/beam/).
- Grupos mistos de colcheias e semicolcheias **não** podem ser exportados
  pelo modelo atual de feixes contínuos, pois exigiriam hooks ou feixes
  parciais. `Measure.issues` agora acusa `mixed_beam_durations`.
- Nenhuma duração é atribuída para completar compassos artificialmente.
  MusicXML continua recusando compassos incompletos e notas de altura
  ou duração não resolvida.

## Evidência geométrica exigida

Para dois candidatos preenchidos com hastes de mesma direção e sem barra
de compasso aceita entre eles:

1. Há continuidade de tinta ao longo da faixa primária entre as pontas.
2. Há continuidade de tinta em uma **segunda faixa** separada, na direção
   da cabeça e à distância proporcional ao espaçamento da pauta.
3. O espaço intermediário é predominantemente **sem tinta**, evitando
   aceitar um único traço extremamente grosso como dois feixes.
4. **Todos os pares adjacentes** de um componente conectado devem ter
   os dois feixes completos para aceitar duração de semicolcheia em todo
   o grupo. Presença de feixe secundário apenas em parte do grupo,
   evidência intermediária ou faixa mesclada mantém a classificação
   `inconclusive` com diagnóstico.
5. Uma confirmação de haste ausente ou uma barra separadora impede a
   associação. A representação não prevê feixes de notas em múltiplas
   vozes nem ritmos diferentes dentro do mesmo grupo.

O método é uma heurística visual explícita e pode falhar com edições de
densidade maior, feixes inclinados, cruzamentos e remoção de pautas.
O limiar intermediário foi escolhido como restrição conservadora;
**não foi calibrado usando o conjunto de teste reservado**.

## Evidência de execução

[GitHub Actions no corpus publicado](https://github.com/kelwin-feitosa/FluteOMR/actions/runs/43077088771),
BWV 1013, página 1, 200 DPI:

| Indicador | Antes | Depois |
| --- | ---: | ---: |
| Eventos de nota propostos | 412 | 412 |
| Alturas numéricas propostas | 402 | 402 |
| Durações determinadas | 72 | **82** |
| Semicolcheias propostas | 0 | **10** |
| Durações inconclusivas | 340 | **330** |
| Durações inconclusivas por feixe duplo | 319 | **309** |
| Durações inconclusivas por haste não confirmada | 21 | 21 |

Esses dez candidatos adicionais **não foram conferidos contra ground
truth musical independente**; logo não se pode atribuir ganho de precisão.
A partitura permanece incompleta e não foi exportada como MusicXML final.

Os testes controlados usam desenhos independentes do detector e examinam
grupos completos, feixes parciais, faixas grossas, barras de compasso,
combinações proibidas e representação MusicXML de dois níveis.
Outras resoluções foram testadas geometricamente em experimentos
anteriores, mas ainda não há resultado quantitativo confiável de ritmo
para cada DPI.

## Riscos e próximos incrementos

- Um segundo traço cortado por artefatos de pauta pode continuar inconclusivo.
- Feixes secundários parciais de grupos mistos exigem modelar **beam hooks**
  e posições individuais por nível, não apenas a categoria do grupo.
- Múltiplas vozes, ligações e barras de compasso precisam ser estudadas em
  exemplos de edição real anotados.
- Conferir as dez novas durações contra a gravura e referência derivada
  da mesma edição; até então são hipóteses classificadas.
- Uma referência MusicXML gerada por conversão automática do LilyPond
  original deve ser registrada como `source_derived_unreviewed`, jamais
  como revisão humana. Só comparar musicalmente depois de comprovar a
  correspondência da edição e a qualidade dos eventos.
