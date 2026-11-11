# Preparação de corpus real para FluteOMR

Este documento é uma **triagem de fontes e um protocolo de preparação**, não um
conjunto de partituras anotadas nem um benchmark com resultados medidos.

## Fontes candidatas e direitos

| Fonte | Evidência publicada | Relevância e cautela |
| --- | --- | --- |
| [OpenScore Lieder](https://github.com/OpenScore/Lieder) | Repositório de partituras digitais CC0, com fontes MuseScore e conversão para MusicXML/PDF | Boa fonte de referência autoral digital e experimentos de gravura; muitas obras contêm voz e piano, portanto não devem entrar automaticamente no benchmark de flauta solo |
| [OpenScore Lieder — derivado Hugging Face](https://huggingface.co/datasets/guangyangmusic/OpenScore-Lieder) | Seleção derivada de 64 exemplos de páginas, com imagens e MusicXML; licença declarada CC BY 4.0 | Verificar correspondência página/partes e respeitar atribuição; não classificar como referência revisada por humano para o FluteOMR sem inspeção |
| [MUSCIMA++](https://ufal.mff.cuni.cz/muscima) | Imagens manuscritas e anotações de símbolos, CC BY-NC-SA 4.0 | Não representa o alvo inicial de gravuras limpas; uso comercial/redistribuição exige avaliação jurídica, portanto não importar no corpus padrão |
| [IMSLP](https://imslp.org) | Arquivo de partituras históricas digitalizadas | Direitos dependem da obra, edição e jurisdição; proíbe assumir licença uniforme |
| [DoReMi](https://github.com/steinbergmedia/DoReMi) | Possível fonte de dados musicais | Licenças de conteúdo, anotações e redistribuição devem ser verificadas para cada artefato antes de importar |

A licença da referência digital não certifica a correção de sua transcrição.
Diferencie sempre **impresso real**, **renderizado digital**, **sintético**,
**source_authored** e **revisado por humanos**.

## Fluxo reproduzível sem versionar material de terceiros

1. Conferir direitos e descarregar o PDF localmente em diretório não versionado.
2. Extrair uma página com metadados e hashes por meio do rasterizador próprio.
3. Abrir a imagem, identificar o recorte que corresponde a uma pauta de flauta
   em clave de sol e configurar limites de compasso manualmente.
4. Preparar pacote de revisão com a CLI existente.
5. Criar ou corrigir a referência MusicXML **sem aceitar a predição do OMR
   como verdade**, se possível conferindo por outro músico.
6. Confirmar explicitamente a revisão humana, mantendo hashes e `work_id`
   consistentes; preservando divisão fixa por obra.
7. Avaliar primeiro development; validação e test separados.

Exemplo (ajuste todos os caminhos, parâmetros e licenças ao material efetivo):

```bash
python -m tools.extract_pdf_page fonte.pdf \
  --page-number 1 --dpi 200 \
  --output outputs/real/original-p1.png \
  --metadata outputs/real/original-p1.json \
  --source-url 'https://example.org/origem-confirmada' \
  --license-id 'CC0-1.0'

python -m tools.music_review prepare outputs/real/original-p1.png \
  --output-dir outputs/reviews/obra-p1 \
  --id obra-p1 --work-id obra-id-estavel \
  --crop 0 0 1200 400 --scale 1 \
  --measures 1 --measure-left 100 --measure-right 1100

python -m tools.music_review check outputs/reviews/obra-p1/manifest.json
```

O recorte, os limites e o `work_id` acima são ilustrativos e **não devem ser
copiados sem inspecionar a partitura**. Se houver candidata MusicXML,
adicione `--candidate caminho/para/referencia.musicxml` no preparo, mas mantenha
`draft` até revisão humana independente.

A confirmação deve ocorrer somente depois de conferir o material:

```bash
python -m tools.music_review confirm outputs/reviews/obra-p1/manifest.json \
  --reviewer 'revisor-real' --confirm-reviewed
```

O nome ilustrativo `revisor-real` **não autoriza simular validação**. O agente
de IA pode preparar pacotes e verificar hashes, mas não deve acionar
`--confirm-reviewed` sem confirmação do músico.

## Métodos de avaliação

`tools.evaluate_corpus` verifica separação por obra e, quando presente,
SHA-256 das imagens. O padrão `development` não abre `test`. Referências
`source_authored` têm métricas isoladas de `validated` e falhas são contadas.

```bash
python -m tools.benchmark_integrity --require-work-id \
  outputs/reviews/obra-p1/manifest.json
```

A seleção de avaliação deve ser feita após acumular **obras distintas**;
variantes de uma mesma obra nunca são observações independentes de generalização.

**Faltam dados reais independentes:** não houve downloads ou anexação de
partituras de terceiros nesta implementação. A etapa prática seguinte é
selecionar obras legalmente utilizáveis e preparar referências humanas.
