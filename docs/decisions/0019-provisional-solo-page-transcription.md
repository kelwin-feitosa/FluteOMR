# 0019 — Transcrição provisória de páginas solo

## Problema

A CLI musical exigia uma imagem com exatamente uma pauta e limites x manuais.
Isso impedia sequer obter um diagnóstico musical de uma página comum com várias
pautas. A geometria de página já era detectada, mas não consumida pelo pipeline.

## Decisão

Adicionar `fluteomr.document.transcribe_page` e `tools.transcribe_page`, mantendo
as CLIs existentes. O usuário deve declarar `layout=solo`: cada pauta continua
a mesma parte e recebe um sistema por configuração. Isso não é inferência de
instrumentos nem agrupamento de conjuntos. Clave de sol, 4/4 e eventual identidade
de flauta também são configuração.

Extrair `transcribe_staff_measures` do pipeline existente para reutilizar uma
pauta e limiar já calculados. A função legada preserva a exigência de uma barra
interna; na página, nenhum candidato interno significa um intervalo provisório.

As pautas são processadas sequencialmente em recortes verticais limitados pelos
vãos entre pautas vizinhas, com contexto de até sete espaços. As linhas locais
são transladadas da detecção original, sem redetectar nem redimensionar a pauta.
Notas, regiões, candidatos e compassos voltam às coordenadas da página orientada
por EXIF. Página e índice de pauta ficam em cada nota, e compassos recebem ordem
contínua. IDs de sistema têm origem `configuration`, nunca reconhecimento.

Uma clave visual aceita limita o início da busca. Se não for resolvida, a pauta
falha; `--allow-clefless` é uma opção explícita para exercícios sem clave impressa.
Fórmula e armadura não são reconhecidas. Uma margem extra pode ser fornecida em
espaços de pauta. O fim segue a convenção já usada nos exemplos: extensão da
pauta menos 0,6 espaço, para não tratar sua borda como barra interna.

## Resultado e limitações

O JSON preserva resultados parciais e falhas por pauta, sem afirmar correção.
`ready_not_validated` significa apenas ausência de problemas conhecidos. Qualquer
pauta incompleta/falha bloqueia a exportação final; não se inventam eventos ou
compassos para preencher lacunas. Código de saída 1 preserva JSON parcial;
problemas de entrada/arquivo retornam 2. Arquivos existentes não são sobrescritos.

Testes com duas pautas de raster próprio verificam oito eventos, coordenadas,
ordem, proveniência, falha parcial e MusicXML. Twinkle real passou a ser processado
sem recorte manual, mas gerou 33 eventos em 13 intervalos provisórios e ficou
bloqueado por inconsistências rítmicas. Não possui referência humana validada:
essas contagens não são métricas de precisão. Medição local: 23,16 s, RSS máximo
34.544 KiB; não é benchmark universal.

Continuam fora do escopo: PDF, múltiplas páginas em um único documento, conjuntos,
barras finais/duplas classificadas, reconhecimento exaustivo de símbolos e
garantia de não omissão. Sistemas muito próximos podem limitar contexto de hastes.
