# 0014 — Colcheias por relações entre cabeça, haste e tinta transversal

Esta decisão registra a versão inicial da Sprint 1C-B. A decisão 0015 substitui
as regras de bandeirolas descendentes, distância de feixes, supressão de falsas
cabeças e classificação do antigo exemplo reservado.

O modelo usa `Fraction(1, 2)` de semínima para a colcheia. O exportador MusicXML
usa `divisions=2` somente quando há colcheias; conserva `divisions=1` nas saídas
anteriores. Um feixe confirmado recebe `beam` begin/continue/end; bandeirolas
isoladas usam apenas `type=eighth`. Cabeças, alturas, barras e compassos continuam
no pipeline existente.

Para evitar falsas cabeças em bandeirolas/feixes, o detector exige maior
ocupação do contorno elíptico. Na pauta monofônica, também descarta uma aparente
cabeça vazada quase na mesma coluna de uma preenchida mas distante na vertical.
Essa regra não oferece suporte a acordes nem múltiplas vozes. O detector de ritmo
mede a ponta real de cada haste por continuidade vertical; procura tinta curva ao
lado exterior para bandeirolas e continuidade transversal entre duas hastes para
feixes. Todas as distâncias derivam do espaçamento local da pauta. Uma segunda
faixa paralela produz duração inconclusiva, bloqueando MusicXML final.

Referências MusicXML próprias foram escritas antes da alteração do detector e
renderizadas no MuseScore Studio 4.7.4 a 300 DPI. As imagens geradas ficam em
`outputs/`, não no Git. Três casos de desenvolvimento deram 13/13 eventos
corretos; um caso reservado, com espaçamento horizontal muito maior, deu 3/6
correspondências e três erros de duração, sem MusicXML exportável. Nele, duas
bandeirolas descendentes usam uma curva que a sonda atual não encontra e o par
com feixe tem hastes separadas por cerca de 12,6 espaçamentos, acima do limite
geométrico de oito. Não ajustamos o algoritmo a esse caso. Não há avaliação
independente com partituras reais anotadas. A versão atual é experimental e a
escolha de escalas de página/corte continua manual.

MuseScore permanece uma ferramenta opcional de geração e round-trip. Os testes
automáticos desenham exemplos próprios com Pillow e não exigem sua instalação.
