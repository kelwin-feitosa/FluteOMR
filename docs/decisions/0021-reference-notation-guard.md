# 0021 — Guarda de armaduras, fórmula e claves nas métricas MusicXML

**Data:** 11/11/2026 · **Estado:** implementação experimental

## Problema comprovado

`music_evaluation.parse_reference` lia o tom escrito em cada `<pitch>` e
marcava `<alter>` explícito como não suportado. Entretanto, uma armadura
como Sol maior pode modificar a altura soante de F para F# **sem que
`<alter>` apareça em todas as notas**. O alinhamento anterior poderia então
contar um F natural previsto como correto contra um F# definido pela
armadura, superestimando a precisão musical.

A mesma avaliação não observava fórmula de compasso e clave de referência
diferentes das configurações 4/4 e clave de sol do OMR experimental.

## Decisão

Na leitura da referência MusicXML, acompanhar o estado de `key`, `time` e
`clef` ao longo dos compassos, aplicando-o até uma redefinição explícita.

- `key/fifths != 0`: marcar `key_signature` não suportada.
- Armadura não tradicional sem `fifths`: `nontraditional_key`.
- Fórmula explicitamente diferente de 4/4: `time_signature`.
- Clave explicitamente diferente de G na linha 2: `clef`.
- Alterações individuais, pausas, ligações, várias vozes e movimentações de
  cursor continuam seguindo as regras conservadoras já existentes.

A mudança **não tenta inferir uma armadura ou transpor notas**. O objetivo é
evitar pontuação falsamente alta: compassos não suportados passam a ser
`unevaluable`, com seus eventos preservados nos denominadores e diagnósticos.

## Limitações e próximos passos

`MeasureEvents.unsupported` registra uma razão predominante, não uma lista
exaustiva de todas as razões simultâneas. Atualmente os testes e o reconhecedor
de referência assumem MusicXML partwise sem namespace explícito. Para avaliar
armaduras e fórmulas além do subconjunto atual, expandir os modelos musicais e
as métricas juntas, preservando referências independentes e testes por obra.

Testes cobrem armadura não nula sem `alter`, persistência entre compassos,
retorno a Dó maior, armadura não tradicional, clave, fórmula e `fifths`
malformado.
