# 0015 — Evidência rítmica local e segunda passagem para páginas largas

## Contexto

Na 1C-B, duas bandeirolas descendentes de um exercício MuseScore eram lidas
como semínimas (2/4 eventos completos) e um feixe sintético contínuo era
rejeitado só por separar hastes em mais de oito espaçamentos. Em páginas A4,
uma pauta curta podia ocupar menos de 25% da largura e desaparecer na projeção.
A supressão de falsas cabeças vazadas pela proximidade horizontal também removia
uma mínima legítima próxima de outra nota.

## Decisão

- Procurar curvas junto à ponta livre da haste e exigir extensão horizontal e
  progressão vertical proporcionais ao espaçamento. Hastes descendentes podem
  ter a bandeirola à direita ou à esquerda. Geometria parcial gera duração
  inconclusiva com `weak_flag_geometry`; não vira semínima por padrão.
- Ligar hastes por suporte de tinta ao longo do segmento entre as pontas, sem
  distância máxima fixa, mas rejeitar lacunas superiores a 1,2 espaçamento ou
  uma barra aceita no intervalo. A imagem sem linhas da pauta é usada para
  reduzir confusão com pautas. O teste de espessura isolada foi rejeitado:
  a supressão de linhas também apaga pixels de feixes que cruzam a pauta.
- Exigir tinta nos lados esquerdo e direito do contorno para uma cabeça vazada,
  em vez de eliminá-la pela proximidade de uma cabeça preenchida.
- Se o detector não encontra grupo na projeção normal, repetir a extração com
  comprimento mínimo de 10% da largura; manter o agrupamento e a validação
  existentes. Tentar essa passagem antes de aumentar o contraste. As
  coordenadas permanecem as da imagem de entrada.

## Verificação e limites

Testes sintéticos cobrem três espaçamentos, feixe longo, fragmento, barra entre
hastes, marca curta, duração inconclusiva, mínima próxima e página com margens.
Dois novos exercícios de desenvolvimento passaram de 2/4 para 4/4 e mantiveram
5/5 eventos completos. O caso antes reservado, agora *validation* porque foi
consultado, passou de 3/6 para 6/6. Dois exercícios novos foram congelados
antes da renderização e avaliados uma vez ao final: 9/9 eventos, ambos no
MuseScore 4.7.4 a 300 DPI. Isso é evidência limitada ao renderizador e à
notação controlada, sem referência humana em partitura real.
Apesar do nome `dev_long_beam`/`blind_long_beam`, o MuseScore compactou a
disposição das notas; o alcance superior a oito espaçamentos foi verificado
apenas no desenho sintético direcionado.

Uma execução exploratória da mesma referência `dev_down_flags` a 200 DPI
(página 1654×2338, limites configurados 300–513) encontrou três candidatos,
dois inconclusivos. O compasso inteiro ficou `not_evaluated`; não há taxa de
acerto interpretável para esse caso.
O MuseScore rearranjou as posições horizontais; dois candidatos não tinham
haste confirmada e a mínima final não foi localizada. Como esse experimento
ocorreu após congelar o detector, não houve ajuste posterior. O resultado
mostra que a variação de DPI ainda não está estabilizada.

A primeira passagem de página ainda pode falhar com pautas inclinadas ou muito
curtas; cinco linhas não musicais continuam um falso positivo conhecido. O
limite externo do compasso, a clave e o 4/4 seguem configurados. Feixes duplos,
figuras parcialmente visíveis, pausas e acidentes não são reconhecidos. A
ausência de evidência de bandeirola ainda pode ser classificada como semínima;
uma soma rítmica correta não prova completude óptica.
