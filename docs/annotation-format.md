# Referências anotadas (formato 1)

Uma referência é um JSON por imagem. Coordenadas são inclusivas, em pixels da
imagem após orientação EXIF, com origem no canto superior esquerdo. O SHA-256 é
calculado sobre os **bytes originais** do PNG/JPEG. O nome da imagem é simples,
sem diretório; `--images-dir` define onde procurá-la.

```json
{
  "schema_version": 1,
  "kind": "reference",
  "split": "development",
  "review": {"status": "draft", "confirmed_by": null},
  "image": {
    "id": "exemplo-001",
    "filename": "exemplo.png",
    "sha256": "SUBSTITUA_PELO_SHA256_REAL",
    "width": 400,
    "height": 160
  },
  "coverage": {"staffs": "unknown", "systems": "unknown", "clefs": "unknown"},
  "staffs": [],
  "systems": [],
  "clefs": []
}
```

O valor ilustrativo de `sha256` deve ser substituído por 64 dígitos hexadecimais.
`split` é `development`, `test` ou `unspecified`; referências validadas exigem
os dois primeiros. Use `development` para as quatro imagens usadas na evolução
dos detectores. Reserve `test` para imagens independentes, escolhidas antes de
ajustar os algoritmos. A mesma imagem não pode aparecer duas vezes numa execução.

`coverage` descreve se a lista de cada componente é exaustiva na página:
`complete`, `partial` ou `unknown`. `complete` em pautas exige que todas as
pautas visíveis estejam listadas e confirmadas. Se houver pauta possivelmente
omitida, use `partial`; se não houve revisão, use `unknown`. Métricas globais de
pautas exigem cobertura completa.

Cada item de `staffs` contém `id` único, `order` (0, 1, ...), `review_state`
(`confirmed`, `partial`, `unknown`), `region` e `lines`. A região usa `left`,
`top`, `right`, `bottom`. `lines` é `null` ou lista de exatamente cinco objetos
`{ "x_start": ..., "x_end": ..., "y": ... }`, de cima para baixo. Uma pauta
confirmada exige região; linhas só devem ser preenchidas quando revisadas.
Valores parciais/desconhecidos não entram na correspondência espacial.

Cada item de `systems` contém `id`, `order`, `staff_ids` ordenados,
`review_state` (`confirmed` ou `uncertain`) e `partial_visible` booleano. Uma
pauta não pode estar em dois sistemas confirmados. Cobertura completa de sistemas
exige cobertura completa de pautas e uma partição confirmada delas.

Cada item de `clefs` contém `staff_id`, `state`, `kind` e `region`. Estados:

| `state` | `kind` | `region` | Significado |
|---|---|---|---|
| `present` | `treble`, `bass`, `alto` ou `other` | caixa ou `null` | Símbolo conferido; caixa opcional. |
| `absent` | `null` | `null` | Ausência conferida por humano. |
| `unknown` | `null` | `null` | Não conferido; nunca é negativo. |

Referências validadas exigem um estado de clave por pauta, inclusive `unknown`.
`review.status` começa como `draft`; apenas o comando `confirm` grava
`validated` e `confirmed_by`, depois de conferir imagem e esquema. A confirmação
é uma declaração humana, não uma inferência do detector.
