# 0020 — Rasterização PDF opcional e limites de recursos

**Data:** 11/11/2026 · **Status:** experimental, aguardando revisão de PR.

## Problema

O pipeline musical já processa páginas PNG/JPEG com várias pautas, mas não
possuía entrada PDF. Implementar um parser de PDF próprio não contribui para
a diferenciação científica do OMR, e misturaria problemas de renderização,
segurança e geometria musical.

## Decisão

Adicionar `fluteomr.pdf_io` com pypdfium2/PDFium como **rasterizador apenas**,
sem transferir reconhecimento de símbolos ou interpretação musical a motor externo.

A dependência é opcional via `fluteomr[pdf]` e fixada no ambiente de
desenvolvimento para viabilizar CI. O núcleo de imagens permanece dependente
apenas de Pillow.

A API `pdf_page_count(path)` obtém o total de páginas;
`load_pdf_page(path, page_number=1, dpi=200)` devolve Pillow RGB com
coordenadas no raster, preservando a noção da página de origem.
A CLI existente `tools.transcribe_page` aceita PDF mediante seleção explícita
de página, gerando diagnóstico JSON mesmo quando o MusicXML é bloqueado.

## Segurança e consumo de recursos

- Validar cabeçalho, tamanho e contagem de páginas antes da rasterização.
- Exigir página numerada a partir de um e DPI no intervalo 72–400.
- Calcular dimensões estimadas **antes** de invocar a renderização, rejeitando
  resultados acima de 20 milhões de pixels.
- Manter limitação defensiva inicial de 128 MiB/arquivo e até 1000 páginas.
- Liberar explicitamente página e bitmap nativos também em caminhos com erro.
- Copiar o bitmap Pillow antes de liberar sua memória nativa.
- Não renderizar todas as páginas de uma só vez; uma chamada processa
  exatamente uma página.
- Registrar hash SHA-256 do PDF, número da página e DPI no relatório.
- Nunca sobrescrever saídas existentes.
- Não tratar processamento de PDFs arbitrários como seguro em processo sem
  isolamento: a biblioteca nativa precisa de sandbox para dados não confiáveis.

O limite de pixels é herdado de `image_io.MAX_PIXELS` para respeitar o
ambiente-alvo Linux/i3/8 GiB. Não implica que todo arquivo permitido será seguro.

## Alternativas consideradas

- **PyMuPDF:** boa renderização; licenciamento AGPL/comercial exige estudo
  jurídico adicional antes de adoção no produto.
- **Poppler/pdftoppm:** ferramenta do sistema, mas acopla o projeto à instalação
  externa e à gestão de processos; pode ser um fallback futuro.
- **pypdfium2:** bindings leves, distribuição em wheels e licenciamento
  Apache-2.0/BSD-3-Clause para o wrapper, com licenças complementares dos
  binários e dependências. Documentação:
  https://pypi.org/project/pypdfium2/ e
  https://pypdfium2.readthedocs.io/en/stable/python_api.html.

Não utilizar pypdfium2 como reconhecedor de notas. PDF renderizado continua
passando por detectores próprios do FluteOMR.

## Verificação e limitações

Os testes criam PDFs vetoriais próprios, verificando número de páginas,
renderização da página solicitada, cores, erros de seleção, arquivo inválido,
limite prévio de pixels e integração com a CLI sem mascarar a saída incompleta.

Não há inferência automática de layout, armadura, fórmula, pausas ou
transcrição de todas as páginas num único MusicXML. A rastreabilidade atual
usa página e DPI, mas a coordenada musical está no raster PDF normalizado,
não em pontos originais do PDF; futuras projeções de coordenadas precisarão
de transformação explícita.

A implementação não é evidência de precisão musical em partituras reais.
