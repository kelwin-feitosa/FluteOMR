# Corpus publicado de flauta — primeira aquisição e baseline geométrico

**Execução original:** 11/11/2026 · **Status:** dados adquiridos e geometria
efetivamente processada no GitHub Actions. Nenhuma precisão de notas foi medida.

## Obras efetivamente obtidas

| ID | Publicação | Direitos declarados | PDF de origem | SHA-256 verificado no download | Páginas |
| --- | --- | --- | --- | --- | --- |
| `mutopia-bwv1013` | J. S. Bach, Partita BWV 1013, flauta solo; gravura Jacob Shapiro, Mutopia 1528 | Dedicação de domínio público pelo gravador | [BWV 1013](https://www.mutopiaproject.org/ftp/BachJS/BWV1013/bwv1013/bwv1013-a4.pdf) | `f73c6e478af78237ebf0cf2e9842cf111937e76e6e5e018bb85e5be729a31d47` | 5 |
| `mutopia-bwv1031` | Siciliano BWV 1031, flauta e violão, gravura Mutopia 1535 | Domínio público declarado na edição | [BWV 1031](https://www.mutopiaproject.org/ftp/BachJS/BWV1031/bach_siciliano_bmv_1031/bach_siciliano_bmv_1031-a4.pdf) | `d7d83ef363064d5eeab66ed6d41642983962b422aeefb9a527472e39ca613abb` | 2 |

Fontes de licença das edições:
[Mutopia 1528](https://www.mutopiaproject.org/cgibin/piece-info.cgi?id=1528) e
[Mutopia 1535](https://www.mutopiaproject.org/cgibin/piece-info.cgi?id=1535).
A verificação de domínio público refere-se às declarações das **edições
específicas**, não a todo o acervo Mutopia nem a qualquer versão alternativa.

Os dois códigos LilyPond publicados foram obtidos pelo GitHub do Mutopia e
preservados em `tests/data/real_scores/`, com os hashes do Git upstream no
catálogo. Os PDFs foram baixados em execução real, tiveram seu SHA-256
calculado, e ficam apenas em **artefato privado temporário de GitHub Actions**
e nas saídas locais reproduzíveis. Não foram adicionados como blobs Git.

Ambas são gravuras musicais digitais de obras publicadas por terceiros,
**não são scans históricos e não foram sintetizadas especialmente para testar
o FluteOMR**. A obra BWV 1031 tem várias partes e não deve ser tratada
como exemplo de transcrição solo suportada.

## Baseline geométrico executado

Execução [GitHub Actions #8](https://github.com/kelwin-feitosa/FluteOMR/actions/runs/43016519438):
`python -m tools.fetch_public_scores` + `python -m tools.real_staff_baseline`
sobre os PDFs realmente obtidos.

| Obra | Página PDF | 150 DPI | 200 DPI | 300 DPI |
| --- | ---: | ---: | ---: | ---: |
| BWV 1013 | 1 | 11 | 11 | 11 |
| BWV 1013 | 2 | 12 | 12 | 12 |
| BWV 1013 | 3 | 14 | 14 | 14 |
| BWV 1013 | 4 | 14 | 14 | 14 |
| BWV 1013 | 5 | 13 | 13 | 13 |
| BWV 1031 | 1 | 10 | 10 | 10 |
| BWV 1031 | 2 | 12 | 12 | 12 |

Total: **2 obras, 7 páginas, 21 rasterizações/detecções** e contagens
consistentes entre as 3 resoluções para todas as 7 páginas. Todos os
resultados do detector tiveram `status="detected"`.

As visualizações de diagnóstico foram examinadas em 200 DPI para as páginas
1 e 2 de ambas as obras e confrontadas com as pautas publicadas. Essa inspeção
qualitativa é **preliminar e não é uma anotação musical humana independente**.

O resultado demonstrou robustez de contagem neste pequeno conjunto, mas
**não certifica 100% de acerto geométrico universal**. O relatório conserva
`reference_staff_count=null`, `staff_accuracy="not_evaluated"` e
`musical_event_accuracy="not_evaluated"`. Nenhum número de precisão de notas
pode ser derivado dessas contagens.

As medições de tempo na execução GitHub Actions não representam a velocidade
no i3-7100 local.

## Reprodução e integridade

```bash
python -m tools.fetch_public_scores \
  --catalog tests/data/real_scores/sources.json \
  --id mutopia-bwv1013 --id mutopia-bwv1031 \
  --out-dir outputs/real_scores

python -m tools.real_staff_baseline \
  outputs/real_scores/mutopia-bwv1013/source.pdf \
  --page 1 --page 2 --page 3 --page 4 --page 5 \
  --dpi 150 --dpi 200 --dpi 300 \
  --report outputs/real_scores/mutopia-bwv1013/geometry.json \
  --preview-dir outputs/real_scores/mutopia-bwv1013/previews
```

Para a edição BWV 1031, faça `--page 1 --page 2` com o caminho correspondente.

O downloader recusa URLs fora da lista permitida, limita a 20 MiB por PDF,
confere cabeçalho e final, valida SHA-256 fixado e nunca sobrescreve material
anterior. A aquisição depende de disponibilidade pública do servidor; o
workflow de corpus fica separado dos testes offline para não tornar o CI
básico refém da rede.

## Rastreabilidade e limitações científicas

- **Obras:** 2, com `work_id` distinto por edição.
- **Páginas:** 7, sem contagem artificial de 21 obras independentes.
- **Referências MusicXML independentes correspondentes:** 0.
- **Referências musicalmente revisadas por humanos:** 0.
- **Testes em manuscrito escaneado histórico:** 0.
- **Métricas musicais de altura/duração/compasso:** `not_evaluated`.
- **Avaliações do subconjunto solo:** somente geometria das páginas de BWV
  1013; BWV 1031 é caso negativo para uma futura seleção de parte.
- **Conjunto reservado test:** não consultado nem utilizado em parametrizações.

Próxima etapa: estruturar um primeiro MusicXML correspondente independentemente
ao impresso; documentar páginas/compassos/edição; submeter a revisão humana;
medir cobertura e erros do reconhecedor para o subconjunto suportado.
Se não houver evidência suficiente, continuar registrando falhas e evitando
exportação musical não verificada.


## Diagnóstico musical de página publicada — sem referência independente

No [Actions #13](https://github.com/kelwin-feitosa/FluteOMR/actions/runs/43017334483), o programa `tools.real_music_probe` executou
o motor próprio de OMR **sobre a página 1 completa** do PDF BWV 1013, a
**200 DPI**, sem ler referência MusicXML e sem produzir exportação final:

| Indicador observável | Resultado |
| --- | ---: |
| Pautas detectadas | 11 |
| Compassos *propostos* pelo motor | 22 |
| Eventos de nota *propostos* | 412 |
| Predições com altura numérica | 402 |
| Predições com duração determinada | 72 |
| Predições sem duração determinada | 340 |
| Diagnósticos registrados | 39 |
| Tempo de inferência na máquina virtual do GitHub | 93,3802 s |
| Precisão musical | **não avaliada** |

**402 alturas calculadas não significam 402 alturas corretas.** Não existe
ground truth MusicXML correspondente e independente neste experimento.
A maioria dos eventos identificados não tem duração resolvida (340/412),
em parte porque a partitura contém grupos de semicolcheias, fora do
subconjunto de duração implementado. O motor preservou a incerteza. Nenhum
MusicXML foi exportado por essa sonda.

O resultado evidencia duas prioridades: (1) tratar durações de alta densidade
(semicolcheias, feixes duplos e posições provisórias) sem fabricar ritmos, e
(2) investigar o custo computacional do pipeline em página inteira. O tempo de
93 s foi medido em um runner do GitHub, não no computador do usuário.

Essa sonda **não fornece precisão nem taxa de erro**, pois não há comparação
com referência musical independente; fornece cobertura provisória e tempo
de execução sobre obra publicada.
