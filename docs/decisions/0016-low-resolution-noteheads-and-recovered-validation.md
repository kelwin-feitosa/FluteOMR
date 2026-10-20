# 0016 — Cabeças de baixa resolução e recuperação da validação

## Evidência e decisão

Em `dev_down_flags`, a pauta a 200 DPI estava correta (espaçamento aproximado
de 14 px, contra 20,75 px em 300 DPI). Os centros musicais acompanham a escala;
a hipótese de rearranjo horizontal registrada na decisão 0015 não se confirmou.

A supressão apagava `floor(y-thickness/2)..ceil(y+thickness/2)`: uma linha de
1 px podia apagar três linhas do raster. Agora arredondamos a primeira linha
de `y-(thickness-1)/2` e removemos exatamente `thickness` linhas, preservando o
suporte vertical. Na deduplicação, diferenças pequenas de pontuação podiam
selecionar uma sonda deslocada sem haste. Priorizamos a associação com haste
entre sondas que já passaram na geometria da cabeça, sem inflar a pontuação.
As distâncias anteriores de deduplicação permanecem, inclusive seus limites
para acordes e vozes simultâneas.

Essas correções recuperaram três notas, mas a mínima vazada continuava perdida
pela quantização do anel. Para espaçamento <16 px, a transcrição usa uma região
local ampliada bilinearmente a 20 px/espaço. Essa escala fica no intervalo já
exercitado pelo detector; não é inferida da soma rítmica nem da referência.
A região inclui contexto horizontal e vertical para hastes e linhas
suplementares; a página inteira não é ampliada. Cabeças e caixas são mapeadas
de volta com as escalas reais dos dois eixos e arredondamento ao pixel.
A primeira tentativa substituía todas as cabeças pelas ampliadas e piorou um
feixe pequeno: o nativo corrigido tinha 5/5 eventos, a substituição produzia
sete candidatos e dois inconclusivos. A versão final preserva todos os
candidatos nativos e adiciona somente cabeças vazadas ausentes, com cavidade
fechada e haste reconfirmadas no raster original. Sondas nativas correspondentes
não são sobrescritas. O ritmo continua na imagem original. O modo nativo
permanece disponível.

A banda mais estreita também revelou uma falsa cabeça vazada em um feixe
cruzando a pauta a 300 DPI. A geometria de anel, sozinha, não garantia uma
cavidade. Exigimos branco central fechado antes da supressão, com conectividade
4 e área mínima de 4% de `spacing²`. No caminho normalizado, essa verificação
usa o recorte ampliado. A pauta pode dividir a cavidade. Isso evita o contorno
aberto entre haste e feixe; anéis quebrados podem continuar perdidos.

## Alternativas e contrato

A ampliação da página inteira foi descartada pelo custo; métodos de
interpolação testados isoladamente não resolveram de forma consistente a perda
de tinta causada pela supressão. Não afrouxamos globalmente os limiares do anel.
Nenhum modelo, dependência ou código externo foi incorporado.

`detect_noteheads` mantém a execução nativa por padrão e aceita `normalize=True`.
As duas funções de transcrição ativam a normalização local por padrão, com
`normalize_heads=False` para comparação; a CLI oferece `--native-heads`.
Uma cabeça ampliada registra `staff_space_normalized`, sem probabilidade.

Recuperamos também as mudanças interrompidas: `Instrument.flute()` e
`--instrument flute` registram configuração explícita (som
`wind.flutes.flute`, MIDI MusicXML 74); ausência de configuração continua
desconhecida. Sequências de feixe inválidas bloqueiam exportação. O avaliador
não achata `backup`/`forward`, múltiplas vozes/pautas ou ligaduras como melodia
correta, e rejeita graus inválidos e durações não positivas. Referências
incompletas não são promovidas a validadas.

## Verificação e limites

Fixtures raster pequenas derivam de exercícios próprios com referência MusicXML
escrita antes da inferência. `raster/provenance.json` registra cortes, hashes,
DPI e renderizador histórico; a fonte musical não foi registrada. São
desenvolvimento consultado, não teste cego nem material de terceiros.

- `dev_down_flags`: 200 DPI passou de 3 candidatos/2 inconclusivos a 4/4 eventos
  com altura e duração corretas; 300 DPI manteve 4/4. Páginas completas e
  recortes foram avaliados, sem consultar a referência durante a inferência.
- Desenvolvimento anterior: 13/13; validação consultada: 6/6; dois exercícios
  adicionais de desenvolvimento: 9/9. Os testes anteriores de feixes, hastes,
  deduplicação, barras e bloqueio de figuras não suportadas permanecem.
- Feixe reduzido por Lanczos a 80% e 2/3: 5/5 eventos em cada escala. Um teste
  reproduziu a regressão da substituição integral antes da recuperação seletiva.
  Isso é reamostragem controlada, não renderização independente a 200 DPI.
- MuseScore disponível na retomada: 4.7.5, sem reinstalação. Importação e
  round-trip são verificações opcionais de intercâmbio, não validação por XSD
  nem prova de precisão óptica.
- Verificação final: 240 testes aprovados e dois `xfail` anteriores preservados;
  Ruff lint/formatação, `pip check`, CLI legado e `git diff --check` aprovados.
  O round-trip das quatro notas reconhecidas a 200 DPI preservou graus, oitavas,
  durações e identidade instrumental. A avaliação de contagem manteve 34/34 pautas.

Os exemplos reais locais continuam exploratórios sem referência musical humana
validada. Nenhum conjunto reservado foi usado para ajustar esta correção.
Por segurança, a recuperação não substitui nativos e pode omitir uma cabeça
vazada adicional muito próxima de outro candidato. Não há suporte novo a acordes.
Não acrescentamos símbolos musicais. Próximo passo: variar a renderização real
de feixes e cabeças a 150/200 DPI e anotar trechos externos antes de afirmar
generalização entre fontes ou renderizadores.
