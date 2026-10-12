# 0003 — Recuperação de pautas claras e validação geométrica

Estado: adotada. Complementa 0002; não altera o significado de `threshold`.

## Evidência e decisão

Nas quatro imagens locais, a versão 0002 detectou 8, 0, 1 e 3 pautas. Em *Pirates*,
as 50 linhas candidatas incluíam as duas pautas perdidas; desvios de 7/9 pixels
ultrapassavam a tolerância de 15%. Em *Quando*, Otsu 182 recuperou apenas 12
candidatos, pois as linhas suavizadas exigiam um limiar mais claro. Em *Mov. III*,
58 de 60 linhas eram candidatas; duas sumiam no limiar, e extensões diferentes e
espessura de até 2 px inviabilizavam vários grupos. *Twinkle* não falhou.

O limiar de análise avança 30% da distância entre Otsu e o tom mais frequente.
Se não há grupos, uma única segunda tentativa usa 90% do caminho entre o pixel
mais escuro e esse tom. `threshold` continua sendo Otsu; `analysis_threshold`
é um campo adicional, e `contrast_threshold_adjusted`/`contrast_retry` são novos
diagnósticos. A busca adicional custa tempo somente quando necessária.

Aceitamos desvio de até 20% da mediana dos quatro espaçamentos, espessura até 50%
do espaçamento e interseção horizontal de pelo menos 60% da menor extensão.
Continuamos exigindo cinco linhas reais candidatas: não há interpolação silenciosa.
Extremos x e regiões mantêm seu significado anterior.

## Alternativas e consequências

Projeção por janelas poderia recuperar pautas curtas ou inclinadas, mas aumentaria
combinação de candidatos e falsos positivos; não foi necessária para os casos
inspecionados. Uma binarização local por pixel também seria mais custosa e requereria
ajuste de tamanho de janela. Optamos por um segundo limiar global condicionado
à ausência de grupos, mantendo Pillow e o custo proporcional aos pixels.

As contagens visuais revisadas são 10, 9, 12 e 3 (total 34); os valores relatados
originalmente de 10 para *Quando* e 13 para *Mov. III* não correspondem às pautas
visíveis. Um manifesto versiona apenas nomes e contagens; as imagens continuam
ignoradas. Igualdade de contagem não confirma correspondência espacial. Faltam
anotações de linha para medir recall e falsos positivos em imagens reais.

## Revisão 2.1 — limites horizontais

Uma linha podia continuar à direita após uma lacuna ou deslocar-se um pixel na
rasterização. A extração guardava apenas o maior trecho de cada linha isolada.
No *Mov. III*, isso encurtava `x_end`; a região da 12ª pauta parava em 649,
embora as linhas visíveis terminem perto de 743. A região era o envelope dos
candidatos, logo também perdia o fim quando todos estavam encurtados.

Após validar espaçamento e espessura, reunimos evidências da linha em uma faixa
vertical de raio relacionado à espessura, limitado pelo espaçamento. Trechos
separados são aceitos se tiverem pelo menos duas vezes o espaçamento ou 5% do
comprimento típico da linha e estiverem próximos aos limites medianos das cinco
linhas da mesma pauta. Só depois validamos a sobreposição horizontal. Não usamos
a posição de outras pautas; uma pauta realmente curta conserva seu limite.

`candidates` retém os limites brutos para diagnóstico. `staffs[*].lines` recebe
os limites refinados; `region` torna-se o envelope dos limites refinados. Campos,
tipos, coordenadas inclusivas, status e interface da CLI permanecem compatíveis.
Os testes sintéticos cobrem lacunas escalonadas, símbolos perto do fim, pautas
alinhadas de comprimentos distintos, margem em branco e fragmentos isolados.
Sem anotações de extremos nas imagens reais, a avaliação nelas continua visual.
