# 0017 — Corpus, denominadores e evidência compacta de cabeças

## Contexto e protocolo

A auditoria local não encontrou referência musical humana validada para as
16 partituras externas. MusicXMLs em `outputs/` eram predições ou round-trips,
nunca ground truth independente. Os quatro exemplos reservados não foram
abertos; já tiveram exposição histórica à detecção de layout. Twinkle, Fairy
Tail e Blue Bird permanecem desenvolvimento exploratório. O inventário com
hashes e tarefas humanas está em `outputs/sprint-1d/materials-audit.json`.

Criamos três exercícios próprios com referência MusicXML antes da inferência:
dois de desenvolvimento e um de validação. O detector foi congelado antes de
renderizar/avaliar a validação; seus resultados não orientaram correções.
São 22 eventos musicais e seis compassos originais, renderizados em Leland e
Bravura a 150/200/300 DPI: 18 imagens, 132 instâncias de eventos e 36 instâncias
de compassos de referência. Variantes da mesma obra compartilham `work_id` e
split. A validação agora foi consultada e não é teste cego futuro.

MuseScore 4.7.5 usa as fontes solicitadas por estilos locais; Bravura foi
confirmada no `score_style.mss` exportado. Os PNGs são exportados com margem
de corte de 12 px, sem redimensionamento posterior. Clave e fórmula ocultas
mantêm o experimento no subconjunto configurado: treble, 4/4 e voz única.
Os limites externos vêm da geometria da pauta e de uma margem declarada para
excluir a barra final; só barras internas são inferidas. Isso não representa
entrada arbitrária nem reconhecimento visual de fórmula, clave ou instrumento.
LilyPond e Verovio não estavam disponíveis; nenhum renderizador foi instalado.

## Defeitos reproduzidos e decisões

1. Um feixe fino inclinado preenchia parte suficiente da máscara elíptica e
   gerava muitas cabeças, inclusive com hastes emprestadas de notas próximas.
   Verificamos agora os trechos horizontais da imagem sem pauta em uma faixa
   central de meia distância de pauta. Pelo menos `ceil(0.15 * spacing)` linhas
   (mínimo duas) precisam de largura entre 0,5 e 1,8 espaço. Um feixe continua
   além da cabeça; uma cabeça tem extensão finita. Nem todas as linhas precisam
   passar, preservando linhas suplementares mais longas. Não foram alterados
   os limiares de preenchimento para aceitar um caso específico.
2. A altura partia da última linha e acumulava o espaçamento mediano por toda
   a pauta. No raster com centros 93/103,5/113,5/124/134,5, uma cabeça em 94
   virava inconclusiva apesar de próxima à linha superior (F5). Interpolamos
   entre as duas linhas locais observadas e extrapolamos pelo vão externo.
   A tolerância diatônica e o intervalo suportado continuam iguais.

O teste óptico novo falhou antes da correção (20 eventos para cinco no recorte
de feixe a 150 DPI). Testes adicionais cobrem escalas e linhas locais, e as
regressões anteriores de colcheias, mínimas, linhas suplementares, deduplicação
e barras permanecem. Nenhum OMR externo, modelo ou dependência foi incorporado.

## Avaliação e tratamento de falhas

`evaluate_music` acrescenta resultados por compasso e denominadores de eventos
avaliados/não suportados, preservando os campos antigos. Compassos ausentes ou
extras contam inclusive quando vazios. Conteúdo inconclusivo/não suportado não
vira acerto; permanece não avaliável. O laboratório aceita múltiplos compassos,
referência ausente e filtro de split. Uma imagem que falha conserva todos os
eventos e compassos conhecidos no resumo, como não avaliados. Um teste misto
de sucesso/falha impede o falso resumo de 100% nos compassos processados.

O resumo distingue imagens de obras. Com conteúdo não avaliado, a fração de
correspondências confirmadas sobre a referência inteira é limite inferior,
não acurácia estimada. Um erro de barra pode aparecer como várias inserções e
omissões porque os compassos são pareados por número, sem realinhamento musical.

| Conjunto/resolução | Referência | Preditos antes/depois | Correspondências antes/depois |
|---|---:|---:|---:|
| Desenvolvimento 150 | 30 | 57 → 25 | 8 → 23 |
| Desenvolvimento 200 | 30 | 30 → 30 | 30 → 30 |
| Desenvolvimento 300 | 30 | 31 → 30 | 25 → 30 |
| Validação 150 | 14 | 20 → 12 | 4 → 4 |
| Validação 200 | 14 | 14 → 14 | 14 → 14 |
| Validação 300 | 14 | 14 → 14 | 14 → 14 |

No desenvolvimento a 150 DPI, 29 eventos inconclusivos caíram para zero;
restaram sete omissões e duas inserções por associação a compassos. Apenas
3/12 compassos na união referência/predição ficaram corretos (oito esperados
e quatro extras). Na validação a 150 DPI, cada imagem ganhou um compasso
espúrio; houve dez omissões e oito inserções de eventos, sem exportação final.
As correspondências de 200/300 DPI preservaram também os compassos: 12/12
em cada resolução somando desenvolvimento e validação.

O processamento isolado dos PNGs cortados mediu aproximadamente 6–11 s por
imagem e 31–44 MiB de RSS máximo do processo. São execuções locais únicas,
sem alegação de ganho de desempenho. Relatórios detalhados, CSV, comandos,
hashes congelados e overlays permanecem em `outputs/sprint-1d/`.

Regressões finais: 260 testes aprovados e dois `xfail` conhecidos preservados;
Ruff, formatação, `pip check` e `git diff --check` aprovados. Os cinco exercícios
Pillow anteriores mantiveram 15/15 eventos e a contagem de pautas reais, 34/34.
O MuseScore preservou oito eventos de dois compassos, as durações, os feixes e
o programa MIDI 74 no round-trip do MusicXML reconhecido. Isso é intercâmbio,
não validação por esquema nem acurácia óptica independente.

## Limites e próxima prioridade

150 DPI continua insuficientemente estável: cabeças vazadas desaparecem e suas
hastes podem ser aceitas como barras, deslocando a associação de eventos a
compassos. A melhora em desenvolvimento não se repetiu nas correspondências
da validação a 150 DPI; não houve ajuste posterior a ela. Conteúdo matematicamente
consistente não comprova leitura correta. Exemplos reais seguem sem acurácia
musical calculável e não foram promovidos a referências validadas.

Prioridade seguinte: reproduzir conflitos haste/barra e perda de mínimas em
novos exemplos de desenvolvimento, depois obter transcrição humana independente
de compassos completos de Twinkle. Variar outro renderizador quando disponível,
antes de ampliar símbolos ou afirmar generalização para partituras reais.
