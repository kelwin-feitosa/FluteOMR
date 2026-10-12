# 0007 — Referências revisadas e avaliação espacial

Estado: adotada para a infraestrutura de avaliação; não valida detectores reais.

O formato 1 separa sugestões automáticas de referências. Sugestões e PNGs de
revisão são locais; o rascunho contém geometria proposta, mas seus estados
começam `unknown`/`uncertain`. Somente confirmação explícita gera uma referência
`validated`, vinculada aos bytes da imagem por SHA-256 e às dimensões após EXIF.
O esquema é descrito em `docs/annotation-format.md`. Os quatro exemplos já
usados no desenvolvimento pertencem ao conjunto `development`, jamais ao teste
independente.

## Correspondência e métricas

Pautas confirmadas com região são ligadas um-para-um às predições. Um par é
elegível quando a distância vertical dos centros é no máximo 0,75 vez o
espaçamento de referência, a razão de alturas está em [0,5; 1,8] e a
sobreposição horizontal cobre ao menos metade da menor largura. A atribuição
maximiza primeiro o número de pares e depois minimiza distância vertical
normalizada mais perda de sobreposição. Referências/predições com mais de um
par possível recebem diagnóstico de ambiguidade. Só páginas com cobertura
completa de pautas fornecem TP, FP, FN, precision, recall e F1 globais.
Erros médios de bordas, centros y e extremos x usam apenas pares com anotações
correspondentes.

Sistemas são comparados pelas pautas já pareadas. Contamos sistemas exatos,
divisões, uniões, atribuições divergentes e pares de pautas que deveriam estar
juntos/separados. Agrupamentos previstos como `ambiguous` não recebem métrica
de acerto de sistema. Referências parciais podem fornecer diagnósticos de pares
conhecidos, mas não um número de sistemas completamente corretos.

Claves de sol são avaliadas por pauta pareada. `absent` e claves de outro tipo
confirmadas são negativos; `unknown` fica fora dos denominadores. Uma detecção
inconclusiva em positivo conta como não encontrada e é relatada separadamente.
Quando há caixa de referência, IoU >= 0,3 é exigida para TP; uma caixa errada
conta como FP e FN. Sem caixa, o TP verifica presença na pauta, sem alegar
acerto posicional. Precision de claves fica `not_evaluable` se não houver
negativos confirmados; recall exige positivos. Denominadores zero nunca viram
100% por convenção.

## Consequências

O pareamento global custa pouco para páginas pequenas e evita reutilizar uma
predição para várias referências. Tolerâncias geométricas ainda precisam de
sensibilidade em fontes/resoluções diferentes. Métricas nas imagens de
desenvolvimento são diagnósticas, não estimativas independentes de generalização.
Não foram alterados os detectores, a CLI existente nem dependências.
