# ADR 0029 — Experimento opt-in de perfis verticais de feixes duplos

**Missão 7.0.** O algoritmo padrão continua o da ADR 0027.
O experimento só é ativado explicitamente por `adaptive_secondary=True`
nas APIs ou `--adaptive-secondary` na sonda do corpus público.

## Motivação

Em BWV 1013 (Mutopia), 282 durações inconclusivas foram associadas a
traços secundários ambíguos. A revisão visual de **12 recortes
não validados musicalmente** revelou que algumas gravuras exibem dois
feixes distintos, mas o reconhecedor usa uma distância vertical
pré-fixada de 0,95 do espaço entre linhas de pauta. A distância real
entre os centros de faixas pode ser menor ou variar com gravura/DPI.

Alterar o offset global poderia transformar artefatos em falsas
semicolcheias. Por isso, a alternativa é **opt-in** até que haja
comparação controlada e evidência independente de precisão.

## Algoritmo experimental

Para cada par de hastes já associado ao feixe primário:

1. Amostrar suporte de tinta em linhas paralelas com deslocamentos
   inteiros na direção da cabeça de nota;
2. Procurar a banda primária perto da ponta das hastes;
3. Procurar uma segunda banda candidata a distâncias compatíveis com
   o espaçamento da pauta;
4. Exigir suporte >= 0,78, uma lacuna horizontal limitada e um **vale
   vertical sem tinta (suporte <= 0,30)** entre as duas bandas;
5. Distinguir `confirmed`, `ambiguous`, `weak` e `absent`.
6. Aplicar as mesmas regras conservadoras de grupos inteiros ou mistos
   da ADR 0027. A classificação depende do conjunto de hastes e feixes,
   não apenas de uma faixa isolada.

O custo extra ocorre somente na opção experimental; não acrescenta
dependências grandes ou modelos de ML.

## Testes

Os testes controlados geram do zero:

- Segundo feixe separado a distâncias variáveis do primeiro;
- Grupo misto colcheia + semicolcheias;
- Um feixe simples sem banda secundária;
- Traço muito grosso ou fundido;
- Banda secundária interrompida.

O pipeline padrão e suas saídas devem permanecer inalterados.

## Avaliação no corpus

```bash
python -m tools.real_music_probe \
  outputs/real_scores/mutopia-bwv1013/source.pdf \
  --page 1 --dpi 200 --adaptive-secondary \
  --report outputs/real_scores/mutopia-bwv1013/adaptive-probe-200.json
```

O workflow `real-corpus.yml` gera relatórios separados em 150 e
200 DPI, sem mudar o baseline padrão. Mesmo que o experimento aumente
as durações propostas, **isso não prova ganho de precisão**: o
MusicXML derivado do LilyPond ainda contradiz a fonte publicada
(ADR 0025). Os recortes da ADR 0028 permitem examinar falsos
positivos antes de decidir sobre habilitar a opção por padrão.

Para comparação controlada em 200 DPI, usar o perfil padrão
(`music-probe.json`) e o adaptativo (`adaptive-probe-200.json`).
O workflow agora também gera `adaptive-ab-200.json`:

```bash
python -m tools.compare_adaptive_probes \
  outputs/real_scores/mutopia-bwv1013/music-probe.json \
  outputs/real_scores/mutopia-bwv1013/adaptive-probe-200.json \
  --report outputs/real_scores/mutopia-bwv1013/adaptive-ab-200.json
```

O comparador rejeita fonte, página, DPI, modo ou contagem incompatíveis,
e reporta diferenças em durações resolvidas, feixes e razões de incerteza.
Nenhuma diferença de cobertura equivale a acurácia medida.
Ele não usa MusicXML derivado como rótulo de verdade.

Não utilizar `adaptive_secondary` para geração automática de
MusicXML final como se tivesse sido validada por humano.
