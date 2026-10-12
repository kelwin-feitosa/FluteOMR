# 0002 — Geometria de pautas por projeção horizontal

Estado: adotada. Complementa 0001 com a primeira dependência de execução.

## Escolha e alternativas

Pillow lê PNG/JPEG e gera depuração; binarização Otsu e projeção horizontal são
implementadas no projeto. Usar bytes e operações da biblioteca padrão evita
NumPy/OpenCV nesta fase. Hough ou busca de ângulo atenderiam inclinação, mas
exigiriam mais parâmetros e custo sem necessidade no alvo horizontal inicial.
O núcleo recebe imagens Pillow; arquivos e CLI são adaptadores locais.

## Regras geométricas

Pixels <= limiar Otsu são escuros. Uma faixa candidata exige pelo menos 25% da
largura em pixels escuros e 60% do maior pico horizontal. Linhas curtas isoladas
não bastam. A extensão é o maior segmento que une lacunas de até 2% da largura,
arredondadas ao pixel (mínimo 1); precisa ocupar pelo menos 25% da largura.
Faixas consecutivas são consolidadas; centro y é a média ponderada pela contagem
de pixels, espessura é a altura da faixa e extremos x são medianas entre suas linhas.

Cinco candidatos consecutivos formam grupo se cada espaçamento difere no máximo
15% da mediana, cada espessura é <=35% dessa mediana e a interseção horizontal
ocupa >=80% da menor extensão. Grupos que compartilham candidatos são ambíguos,
sem seleção arbitrária. Não há escore probabilístico. Limiares relativos não são
uma garantia para qualquer resolução, sobretudo quando pixels mesclam linhas.

## Consequências e limites

Processamento local, CPU, sem ML/OMR externo. Custo principal proporcional aos
pixels, sem matriz de floats; imagens acima de 20 milhões de pixels são rejeitadas.
EXIF define orientação e transparência é composta sobre branco antes da análise.

O alvo é horizontal. Linhas inclinadas, fracas, muito interrompidas, pautas estreitas
ou candidatos adicionais entre linhas podem perder grupos. Cinco linhas de papel
pautado/tabelas geometricamente equivalentes não são distinguíveis por este módulo.
O diagnóstico `horizontal_geometry_only` explicita esse limite. A visualização
mostra candidatos e grupos, inclusive quando a detecção falha.

## Critérios verificáveis

Ground truth gerado sem consultar o detector: contagem correta, exatamente cinco
linhas e erro máximo <=2 px; negativos inconsistentes rejeitados, seis linhas
ambíguas. Avaliação distingue casos suportados de falhas experimentais conhecidas,
incluindo papel pautado não musical e rotação de 2°. Precisão em imagens reais
depende de avaliação futura com condições de distribuição verificadas.
