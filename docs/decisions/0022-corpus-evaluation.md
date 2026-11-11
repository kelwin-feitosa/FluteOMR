# 0022 — Execução segura de benchmarks por corpus

**Data:** 11/11/2026 · **Estado:** experimental, com testes automatizados

## Problema

O laboratório `tools.evaluate_music` validava a integridade de um manifesto
isolado. Uma avaliação executada com vários manifestos poderia deixar passar
uma obra em `development` e uma variante da mesma obra em `validation`
ou `test`, mesmo com IDs de imagens distintos. A ferramenta
`tools.benchmark_integrity` já identifica essa situação, mas antes exigia
uma verificação manual separada.

Também havia risco operacional de executar inadvertidamente exemplos do
split `test` ao avaliar um conjunto amplo.

## Decisão implementada

A CLI `tools.evaluate_corpus` recebe múltiplos manifestos e chama
`validate_manifests` **antes de abrir imagens ou referências**.

- `work_id` explícito é obrigatório por padrão (sem fallback silencioso);
- quando disponível, `image_sha256` deve ser um digest hexadecimal de 64 caracteres: a verificação detecta imagens byte-idênticas atribuídas a splits incompatíveis ou obras diferentes, mesmo com IDs divergentes; novos pacotes `music_review` incluem e verificam esse campo automaticamente;

- `--allow-legacy-work-id` só para conjuntos históricos, com aviso;
- sem `--split`, avalia **somente development**;
- `validation` e `test` exigem seleção explícita;
- não aceita work_id compartilhado entre splits incompatíveis;
- cada manifesto pode usar suas próprias imagens; `--images-dir` permite um
  diretório comum opcional;
- falhas de leitura/inferência ficam no relatório, com código de saída 1;
- o resumo mantém as referências `validated` e `source_authored` separadas;
- o relatório apresenta métricas globais e por split, mas não equipara
  referência digital gerada automaticamente a validação musical humana.

Exemplo com imagens previamente renderizadas na pasta `outputs/`:

```bash
python -m tools.evaluate_corpus \
  --manifest tests/data/music_lab/sprint1d/development-manifest.json \
  --manifest tests/data/music_lab/sprint1d/validation-manifest.json \
  --images-dir outputs/sprint-1d/rendered \
  --split development \
  --report outputs/sprint-1d/corpus-development.json
```

Ao avaliar `validation`, substitua por `--split validation` e use outro
arquivo de relatório. **Não execute test para ajustar parâmetros.**

A verificação global de integridade usa somente metadados, portanto não
atesta correção, licença, qualidade nem revisão humana de um dataset.

## Limitações e direção futura

As referências continuam a ser lidas da pasta de cada manifesto pelo
`evaluate_manifest` legado. A forma de apresentar notas incorretas
pode ser estendida com categorias de erro por símbolo quando houver ground
truth independente. O pipeline atual exige que a imagem já tenha sido
recortada para o subconjunto suportado e que os limites estejam no manifesto.

O primeiro corpus independente deve incluir imagens de partitura impressa
real, MusicXML anotado/revisado por pessoas e proveniência explícita;
`source_authored` não é equivalente a essa evidência.
