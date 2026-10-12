# 0005 — Partes lógicas separadas das pautas

Estado: adotada para o modelo, sem identidade instrumental automática.

`Staff` é geometria, `MusicSystem` agrupa pautas de uma faixa da página e `Part`
é uma sequência lógica que pode atravessar sistemas. `ScorePage` guarda sistemas
ordenados e partes. `StaffRef` aponta para `(system_id, staff_index)` e registra
se a ligação foi manual ou hipótese. O instrumento começa desconhecido e só é
preenchido pelo usuário nesta etapa.

`propose_parts_by_order` é uma operação explícita: só propõe vínculos quando o
agrupamento está marcado `grouped` e todos os sistemas têm a mesma quantidade de
pautas. Noutros casos, devolve página sem partes. As funções `add_part`,
`link_staff` e `unlink_staff` permitem construir e corrigir vínculos; cada parte
ocupa no máximo uma pauta por sistema e uma pauta não pode pertencer a duas
partes. As estruturas são imutáveis, de modo que a correção gera nova página sem
alterar os resultados de detecção.

Vincular automaticamente pelo índice vertical em sistemas de tamanhos diferentes
seria ambíguo quando uma parte some. A abstenção evita identidade inventada, mas
requer anotação ou evidência textual futura. O modelo não impõe limite de partes,
não presume flautas e ainda não representa vozes simultâneas nem exporta MusicXML.
