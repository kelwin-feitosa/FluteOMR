# ADR 0028 — Pacote verificável de revisão de ritmos inconclusivos

**Missão 7.0 — material científico de revisão humana, sem ground truth presumido.**

## Motivação

O benchmark publicado BWV 1013, página 1, 200 DPI, manteve
330 durações inconclusivas após o reconhecimento inicial de grupos
mistos de feixes (ADR 0027). Os diagnósticos internos foram:

- `secondary_stripe_ambiguous`: 282 eventos;
- `weak_secondary_stripe`: 27 eventos;
- `stem_not_confirmed`: 21 eventos.

Não sabemos quantos desses eventos correspondem a semicolcheias
verdadeiras; alterar limiares para obter mais classificações seria uma
substituição indevida de precisão por cobertura.

## Procedimento implementado

`tools.prepare_rhythm_review` usa somente o PDF público adquirido por
`tools.fetch_public_scores`, a rasterização existente e o OMR próprio.
Seleciona de modo determinístico até 12 eventos, distribuídos entre
pautas e categorias de incerteza, e cria:

1. PNGs que mostram a nota marcada com contorno vermelho e parte da
   gravura ao redor para avaliar hastes e feixes visualmente;
2. `review-manifest.json` com hash SHA-256 do PDF, DPI, página,
   coordenadas e identificadores da predição, diagnósticos e classe
   da incerteza;
3. `review-template.csv` com campos intencionalmente em branco
   para correção por flautista.

O identificador de revisão depende do hash da fonte, página,
pauta e coordenadas da nota, evitando confusão entre edições.
Nenhum arquivo existente é sobrescrito. Todas as imagens são
**evidências de predição ainda não revisada**: o pacote marca
`reference_quality=none`, `human_review_status=unreviewed` e
`ground_truth=null`.

## Execução

```bash
python -m tools.fetch_public_scores \
  --catalog tests/data/real_scores/sources.json \
  --id mutopia-bwv1013 --out-dir outputs/real_scores

python -m tools.prepare_rhythm_review \
  outputs/real_scores/mutopia-bwv1013/source.pdf \
  --page 1 --dpi 200 --max-cases 12 \
  --out-dir outputs/rhythm_review
```

O workflow opcional `real-rhythm-review.yml` gera artefato temporário
com todos os PNGs, manifesto e CSV, sem misturar esses dados com
referências independentes confirmadas.

## Próximos passos

- Inspecionar as amostras com flautista e registrar alterações no CSV
  sem modificar o PDF de origem.
- Comparar períodos completos, inclusive pausas e acidentes; um
  recorte isolado não estabelece duração correta sem contexto métrico.
- Criar conjunto de validação por obra, isolado do material de ajuste.
- Somente calcular acurácia depois de referências humanas revisadas ou
  derivadas de fonte com correspondência musical demonstrada.
- Estudar posições verticais de dois feixes por perfil de tinta, pois
  a separação geométrica real pode divergir do offset fixo estimado.

## Revisão musical humana parcial — 11/11/2026 (casos 9–12)

Observações fornecidas diretamente pelo revisor flautista formado na EMB.
Estão registradas em [`docs/reviews/bwv1013-page1-observations.csv`](../reviews/bwv1013-page1-observations.csv), vinculadas aos `review_id` originais da página 1 (200 DPI, SHA-256 `f73c6e478af78237ebf0cf2e9842cf111937e76e6e5e018bb85e5be729a31d47`).

- **Caso 9**: quadrado reportado sobre o feixe/colchete, sem confirmação da altura real. Tratar como associação visual incorreta até reavaliação.
- **Caso 10**: quadrado reportado sobre o feixe, não sobre a nota. Altura diatônica correta informada: **Mi5 (E5)**; o OMR havia proposto Si4 (B4).
- **Caso 11**: caixa deslocada para o lado, próxima do símbolo de alteração. Altura diatônica correta informada: **Sol♯4 (G#4)**, incluindo o sustenido confirmado pelo revisor; o OMR propôs Fá4 (F4).
- **Caso 12**: altura diatônica correta informada: **Fá♯5 (F#5)**, incluindo o sustenido confirmado pelo revisor; o OMR propôs Mi5 (E5).

**Escopo rigoroso**: são observações humanas reais sobre altura diatônica e geometria dos casos 9–12, mas **não equivalem à validação integral dos eventos**. Duração, níveis de feixe, acidentes nos demais casos, resto do compasso e eventuais notas omitidas continuam não revisados. O CSV **não deve alimentar métricas de precisão final ou a divisão de teste reservado como ground truth completo**.
