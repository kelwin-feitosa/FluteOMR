# ADR 0026 — Feixes explícitos por nota e por nível (MusicXML 4.0)

**Missão 7.0 — Modelo musical.**

## Decisão

A representação existente `Note.beam` modela somente um nível de feixe,
`begin/continue/end`. Introduzimos o campo opcional
`Note.beam_levels: tuple[tuple[int, BeamPosition], ...]` para oferecer
uma representação explícita por nota dos níveis 1 e 2 (colcheias/
semicolcheias). O conjunto `BeamPosition` inclui `forward hook` e
`backward hook` no nível 2.

O contrato antigo permanece funcional quando `beam_levels=()`: um
`beam` legado de colcheia gera nível 1, e um `beam` legado de
semicolcheia homogênea continua gerando os dois níveis. Em grupos
**mistos**, a representação precisa ser explícita, para não inventar
um feixe secundário que a imagem não comprovou.

`Measure.issues` rejeita ligações interrompidas, níveis duplicados,
segundo nível ausente de semicolcheia ligada, segundo nível numa
colcheia, hooks em nível primário e conflitos entre campos legados
e explícitos. Um grupo misto sem indicação explícita continua recusado.

O exportador `to_musicxml` emite cada nível de maneira independente
(sem sobrescrever estados nem inventar hooks) e mantém
`<type>16th</type>` e durações racionais. Não alteramos a detecção
de símbolos neste incremento.

## Fonte normativa

- [MusicXML 4.0: beam element](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/beam/)
- [MusicXML 4.0: beam-value](https://www.w3.org/2021/06/musicxml40/musicxml-reference/data-types/beam-value/)

A especificação autoriza `begin`, `continue`, `end`,
`forward hook` e `backward hook`, com números de feixe a partir de 1.

## Casos controlados

Os testes cobrem colcheia + 2 semicolcheias, 2 semicolcheias +
colcheia, semicolcheias separadas por colcheia com hooks e casos
inconsistentes. Os casos são criados musicalmente sem consultar o
reconhecedor de pixels. Esses testes atestam a **semântica e
serialização**, não a precisão do OMR em partituras reais.

## Próximo incremento

Associar segmentos de feixe secundário **confirmados visualmente** a
cada haste, com evidências de continuidade, separação, direção e
interrupção; não atribuir durações de semicolcheias em feixes ambíguos.
Manter benchmarks e splits por obra sem fabricar ground truth.
