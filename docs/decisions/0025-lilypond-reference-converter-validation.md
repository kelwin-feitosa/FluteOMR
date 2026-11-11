# ADR 0025 — Candidatos de MusicXML derivados do LilyPond e rejeição de divergências

**11/11/2026 — Missão FluteOMR 6.0.**

## Por que foi necessário

O corpus publicado do Mutopia contém o código-fonte LilyPond original
(Partita em lá menor para flauta, BWV 1013, edição Jacob Shapiro).
Esse arquivo é anterior ao FluteOMR e pode ajudar a construir
candidatos para comparação, **mas não é automaticamente um ground truth
musical nem garante a mesma sequência temporal do PDF**.

A ferramenta externa `ly-to-musicxml==0.1.1` (MIT) foi executada em
GitHub Actions com **LilyPond 2.26.0**, o módulo upstream `python-ly`
e a fonte publicada BWV 1013. O pipeline precisou de ajustes de ambiente:

1. O conversor busca o módulo `python-ly/ly/xml/xml-export.ily`
   nos ancestrais do arquivo, mas o pacote PyPI não o instala automaticamente.
   A execução isolada baixa o upstream de
   `xvb8/ly-to-musicxml` em commit
   `5adbd4d9864ad18368ecb2e4909782ab4bbfd258`.
2. O conversor usa wrapper exigindo LilyPond 2.26.0, incompatível
   com o pacote padrão 2.24.3 do Ubuntu 24.04. O workflow usa o pacote
   genérico Linux **oficial** do LilyPond 2.26.0; não altera o motor
   nem o ambiente de execução padrão do FluteOMR.

[Execução que conseguiu converter a fonte](https://github.com/kelwin-feitosa/FluteOMR/actions/runs/43079398396)
gerou um arquivo MusicXML de 87.828 bytes, inventariado com
**1 parte, 28 compassos, 425 eventos com altura e zero pausas**
(424 do tipo `16th` e 1 `half`).

## Divergência musical CONCRETA — não é uma referência válida

O início literal de `allemande` na fonte publicada é:

```lilypond
r16 e''16 a''16 gis''16
```

É uma pausa de semicolcheia seguida de Mi, Lá e Sol sustenido
(em oitavas escritas de LilyPond). Entretanto, o MusicXML produzido
começa com **E4, B4, E5, D#5**, sem qualquer pausa na exportação.

Portanto:
- A conversão produziu XML parseável, mas **não representa
  adequadamente o início do primeiro movimento da obra**.
- Não usar esse arquivo como `ground_truth`, não o integrar às divisões
  `development`/`validation`/`test` para cálculo de acertos.
- O manifesto marca o candidato como **`rejected_source_prefix_mismatch`**,
  quando o teste de abertura está configurado.
- A anotação `tests/data/real_scores/bwv1013-allemande-start.json`
  contém SHA-256 da própria fonte, trecho literal e quatro eventos
  para comparação. É um **teste parcial de contradição**, não revisão
  humana nem demonstração de equivalência do restante da partitura.

Esse é um exemplo de por que contar eventos ou ter MusicXML bem formado
não comprova transcrição correta. O problema é do **conversor candidato
nesta fonte/versão**, não constitui erro do motor óptico FluteOMR.

## Ferramentas disponíveis

`tools.inspect_lilypond_candidates` aceita:

```bash
python -m tools.inspect_lilypond_candidates \
  --source tests/data/real_scores/mutopia-bwv1013.ly \
  --candidates outputs/reference_candidates \
  --expected-prefix tests/data/real_scores/bwv1013-allemande-start.json \
  --report outputs/reference_candidates/source-candidate-manifest.json
```

São registrados hashes, contagem de compassos, eventos, tipos,
pausas e preview. Um prefixo divergente aparece como
`source_prefix_alignment=mismatch`, e cada candidato lista as
diferenças. Sem cheque, o status é `not_checked`; correspondência
somente do início **nunca** significa alinhamento completo ou revisão
humana. Todas as saídas permanecem descartáveis e fora do repositório Git.

## Próximos passos

- Investigar conversão por movimento, preservando repetições, anacruses,
  pausas, alterações de oitava e compassos; verificar explicitamente
  cada início e final de movimento antes de aceitar referência musical.
- Testar alternativas ao conversor experimental, preferencialmente com
  extração de eventos independente do motor FluteOMR.
- Validar notas, pausas, acidentes, ritmos e alinhamento físico com
  os PDFs da edição.
- Submeter o candidato compatível à revisão humana antes de chamar
  de ground truth verificado.
