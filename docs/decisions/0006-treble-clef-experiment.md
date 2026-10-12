# 0006 — Detector geométrico inicial de clave de sol

Estado: experimental.

## Decisão

`detect_treble_clefs` recebe a imagem e a detecção de pautas; só examina o início
de cada pauta. Usa o limiar Otsu da etapa anterior para isolar tinta escura,
suprime pixels das cinco linhas quando não têm continuidade vertical e extrai
componentes conectados. Um candidato precisa atravessar a pauta, estender-se
acima e abaixo dela, ter largura e área proporcionais ao espaçamento, e
apresentar extensão horizontal nas metades superior e inferior. Um candidato
único produz `detected`; candidatos concorrentes produzem `inconclusive`.
`no_treble` significa ausência de evidência que satisfaça essas regras, não
prova de ausência de clave. A posição é uma caixa inclusiva em pixels. Não há
pontuação probabilística ou template de fonte.

O afastamento mínimo da borda esquerda evita confundir um conector vertical
com a clave, observado no *Mov. III*. A análise é opt-in (`--clefs`), para não
acrescentar custo ou alterar o JSON de chamadas antigas. Pillow continua sendo
a única dependência de execução.

## Evidência, alternativas e limites

Testes sintéticos desenham claves por traços, sem compartilhar padrão com o
detector, em três escalas, junto a armadura/notas e com interrupções. Negativos
incluem pauta vazia, clave de dó estilizada, barra vertical e forma de fá. Na
inspeção local das quatro imagens, as observações foram 10, 9, 6 e 3 claves
aceitas; no *Mov. III*, as seis pautas restantes exibem claves de outros tipos
e não foram aceitas como sol. Isso é inspeção limitada, sem caixas anotadas ou
amostra representativa de fontes, e não mede precisão geral.

Uma comparação de templates seria sensível à fonte e à escala; modelos de ML
exigiriam dados e custo maiores. A geometria é simples e auditável, mas uma
forma diferente ou conectada à armadura pode ser perdida, e um símbolo alto com
curvas semelhantes pode gerar falso positivo. Validar fontes diversas e anotar
caixas reais é a próxima etapa antes de considerar o método confiável.
