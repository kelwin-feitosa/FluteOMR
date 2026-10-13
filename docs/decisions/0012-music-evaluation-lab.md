# 0012 — Avaliação musical independente do detector

O subconjunto atual tem notas monofônicas de semínima/mínima, sem pausas ou
alterações cromáticas. O laboratório recebe uma imagem e MusicXML de referência
em arquivos separados. Infere primeiro; só depois lê a referência. Um MusicXML
simples escrito manualmente usa `divisions=2`, diferente da serialização de
saída, para testar a conversão racional de duração.

As partes são alinhadas por ordem e os compassos por número explícito; eventos dentro de um compasso
usam distância de edição com custo unitário e desempate por substituição.
Registramos correspondências, inserções, omissões, substituições e diferenças
de grau, oitava e duração. Isso mede sequência musical escrita, não posição
visual nem equivalência enarmônica. Compassos deslocados podem gerar múltiplos
erros; o relatório não chama esses números de precisão global. Pausas,
alterações, acordes e eventos inconclusivos suspendem a comparação do compasso
e aparecem como `unsupported`. Exportação XML bem formada, correção dos eventos
e preservação da gravura são verificações distintas.

Na deduplicação, uma construção controlada de candidatos mostrou que a regra
anterior de 1,1 espaçamento na vertical eliminava duas cabeças distintas
separadas por um espaçamento quando próximas em `x`.
Mantemos a supressão ampla apenas quando os centros estão quase na mesma coluna;
para colunas diferentes, exigimos distância vertical menor que 0,65 espaçamento.
Isso preserva o descarte da duplicata observada em Twinkle, mas não garante
suporte a acordes ou vozes simultâneas.

Na elaboração inicial desta decisão, MuseScore não estava no `PATH`. A auditoria
seguinte encontrou um Flatpak de usuário e executou os experimentos descritos
em `0013-musescore-geometry-experiment.md`. Não há dependência de MuseScore em CI.
