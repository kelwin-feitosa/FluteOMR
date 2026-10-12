# 0004 — Agrupamento conservador de sistemas

Estado: experimental.

## Decisão

`group_staffs` recebe pautas já detectadas e ordena suas referências pela posição
vertical. Compara as lacunas entre pautas adjacentes: uma razão >=1,5 entre duas
escalas de lacuna separa sistemas, desde que haja ao menos duas lacunas menores,
elas sejam consistentes e as pautas agrupadas se sobreponham horizontalmente em
ao menos metade da largura da mais curta. O limiar de separação é a média
geométrica das duas lacunas nos lados da maior ruptura. IDs são sequenciais na
página; `staff_indices` preserva a referência à detecção original.

Se as lacunas não distinguem escala interna e externa, cada pauta fica isolada
com status `ambiguous`. Isso inclui partituras solo de várias linhas e conjuntos
com lacunas uniformes. Nesses casos, uma pauta isolada é uma proposta para
revisão, não prova de que constitui sozinha um sistema. Não há contagem fixa de
instrumentos ou confiança probabilística.

## Alternativas e consequências

Um limiar absoluto de distância falha quando a resolução ou a diagramação muda.
Forçar grupos pelo número de pautas poderia acertar um exemplo e errar outro.
Barras e conectores compartilhados podem resolver ambiguidades, mas exigem
análise visual própria e ficam para uma etapa posterior. A sobreposição usa a
largura da pauta mais curta, preservando finais legitimamente curtos.

No *Mov. III* local, as lacunas internas são aproximadamente 28–34 px e as
externas 64 px: resultam três sistemas de quatro pautas. Nas outras três imagens,
as lacunas são quase uniformes e o agrupamento retorna pautas isoladas com
ambiguidade; a inspeção visual sugere sistemas solo, mas a geometria não prova
isso. As imagens reais não são versionadas.
