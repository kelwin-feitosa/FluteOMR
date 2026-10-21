# 0018 — Pacotes rastreáveis de revisão musical

## Contexto

Os anotadores Tkinter/web corrigem geometria de pautas, sistemas e claves.
Não permitem anotar a sequência musical. O manifesto do laboratório já aceita
MusicXML externo e distingue `missing`, `draft`, `validated` e `source_authored`,
mas não vinculava a revisão a um recorte específico e ao conteúdo do XML.

## Decisão

Reutilizar o manifesto versão 1, adicionando o campo opcional `review` com nome
de um arquivo local. `tools.music_review` prepara, verifica e confirma pacotes.
O núcleo sem interface fica em `fluteomr.music_review`.

O pacote contém um recorte PNG, MusicXML candidato opcional, manifesto e
`review.json` versão 1. O último registra:

- Origem por caminho relativo, SHA-256, tamanho e página fornecida.
- Recorte PIL `[left, top, right, bottom]` com right/bottom exclusivos, nas
  coordenadas da imagem orientada por EXIF; transparência composta sobre branco.
- Escala inteira, interpolação bicúbica, tamanho e SHA-256 da imagem derivada.
- IDs de pauta/sistema quando conhecidos e números dos compassos selecionados.
- Estado, revisor e data; após confirmação, hash da referência musical.

Centros de pixels mapeiam por `origem + (derivado + 0.5)/escala - 0.5`.
A verificação reconstrói o recorte para conferir o vínculo geométrico, além dos
hashes. Não redefine o formato das anotações geométricas.

`prepare` nunca confirma. `check` verifica estrutura, integridade e escopo dos
compassos; não prova correção musical. `confirm --confirm-reviewed --reviewer`
exige ação humana, sela o XML atual e muda o manifesto para `validated`.
Arquivos selados não são sobrescritos pelo preparador; uma revisão posterior
exige pacote novo. As escritas JSON são atômicas por arquivo; divergência de
estados entre manifesto e revisão falha de forma fechada.

O avaliador legado permanece compatível. Para pacotes com `review`, verifica
integridade depois da inferência e antes da comparação; o XML não alimenta o
reconhecedor. Estados draft/missing continuam sem métricas. Referências antigas
sem sidecar preservam seu contrato anterior, baseado no estado declarado.

## Consequências e limites

Não há novo editor musical: o humano corrige o candidato no MuseScore e exporta
MusicXML para o pacote antes de confirmar. Hash não prova que houve uma boa
revisão. Categorias sem suporte no avaliador continuam sem pontuação.

Twinkle tem um rascunho visual produzido pelo agente, não uma referência humana
validada. Nenhuma métrica de precisão real resulta dessa preparação. Imagens,
candidatos e projetos MuseScore ficam em outputs/, fora do Git. O conjunto
reservado não é processado nem confirmado por este fluxo de desenvolvimento.
