# Contratos de módulos e política de compatibilidade (experimental)

Estado: 11/11/2026. Este documento descreve o código atual, não promete
cobertura de notação ou estabilidade de API que ainda não foi testada.

## Fronteiras

| Camada | Entradas e saídas atuais | Contrato e limitações |
| --- | --- | --- |
| `image_io` | Arquivo PNG/JPEG ou `PIL.Image` → RGB normalizado | Orientação EXIF aplicada, transparência sobre branco, até 20 milhões de pixels; PDF ainda não é entrada desta API. |
| `staff_detection` | `detect_staffs(image, *, config=StaffDetectionConfig())` → `DetectionResult` | Coordenadas na imagem normalizada, origem no canto superior esquerdo, caixas inclusivas. `status` é `detected`, `no_staff` ou `ambiguous`. `detected` significa geometria horizontal válida, não leitura musical correta. |
| `systems` / `score` | Pautas → sistemas, `ScorePage` e vínculos de `Part` | Modelo **geométrico/de organização**. `Part` aqui tem ID inteiro; instrumento não é inferido de pixels. Hipóteses de associação não devem ser exibidas como confirmações. |
| `transcription` / `music` | Imagem, limites configurados → `MusicScore` / `TranscriptionResult` | Modelo **de eventos musicais**, distinto de `ScorePage`. `MusicPart` tem ID string; clave de sol, fórmula 4/4 e limites vêm de configuração no pipeline atual. Pausas, alterações, armaduras e demais símbolos não têm cobertura geral. |
| `musicxml` | `MusicScore` → MusicXML | A exportação deve rejeitar `issues()` não resolvidas; gerar XML bem formado **não** equivale a validar o esquema MusicXML nem a precisão da partitura. |
| `evaluate_music` | Manifesto, imagens e referências separadas → resultados | Valida `work_id` e splits, executa inferência antes de ler o XML de referência e contabiliza falhas. `validated` exige pacote `review` verificável; `source_authored` é referência gerada, não validação humana. |

## Superfície pública e compatibilidade

- `fluteomr.__all__` é a superfície de importação declarada para geometria e
  organização da página; a presença ali **não é ainda garantia de API estável**.
- `StaffDetectionConfig` é imutável e validada; valores omitidos preservam os
  defaults anteriores. Alterações dos parâmetros devem ser registradas junto
  ao benchmark.
- `transcription`, `music`, `musicxml`, detectores de notas/ritmo e `tools/`
  são interfaces **experimentais**, sujeitas a mudanças revisadas. Não alterar
  os formatos silenciosamente em uma atualização.
- Erros e incertezas devem ser explícitos: `None` para altura/duração ainda
  não resolvida; diagnóstico ou `ValueError` quando a entrada não pode ser
  transcrita ou exportada com segurança.
- Não converter automaticamente `score.Part` em `music.MusicPart`: o primeiro
  agrupa pautas na página; o segundo representa eventos para exportação.

## Política para mudanças futuras

1. Separar correção de defeitos da ampliação de símbolos, e preservar fixtures
   conhecidas quando mudar geometria ou reconstrução musical.
2. Adicionar testes para entradas válidas, inválidas e ambíguas antes de tornar
   um campo obrigatório ou alterar a semântica de `status`.
3. Se um contrato mudar, documentar a migração, acrescentar teste de regressão
   e atualizar os consumidores internos na mesma branch.
4. Não promover uma interface a estável antes de existir corpus real revisado
   por humanos, benchmark independente, política de versão e CI reproduzível.
5. Nunca usar acerto em referência `source_authored` como sinônimo de
   generalização para partituras reais. O resumo do laboratório agora inclui
   `reference_quality.validated` e `reference_quality.source_authored`
   separadamente; a fração agregada legada permanece apenas por compatibilidade.

Ver também [auditoria de 11/11/2026](audit-2026-11-11.md).
