# 0009 — Revisão OMR web local com correções separadas

## Decisão

O editor web usa HTML/CSS/JavaScript locais e `ThreadingHTTPServer` da biblioteca
padrão. O servidor escuta apenas `127.0.0.1` e oferece um catálogo de sugestões
já geradas. Não executa detecção ao abrir uma página. A interface lê o PNG
original e desenha sobreposições em suas coordenadas, com zoom apenas visual.
O Stitch orienta a hierarquia de partitura central e painéis laterais, mas seu
Tailwind/CDN, notas vetoriais, percentuais e exportações demonstrativas não são
reutilizados.

Correções operacionais são salvas em `outputs/web-editor/corrections/`, fora do
JSON de sugestões e do formato de referência científica. Cada arquivo contém
`schema_version: 1`, `kind: operational_corrections`, SHA-256 da imagem e das
sugestões, `revision` e `decisions` indexadas por `s0`, `s1`, etc. Uma decisão
explícita é `present` com `kind` e caixa, ou `absent` sem tipo/caixa. A ausência
de decisão conserva a predição automática sem atribuir confirmação humana.
O servidor valida limites, identificadores e hashes e salva por troca atômica.
`base_revision` impede que uma aba sobrescreva silenciosamente outra.

## Segurança e alternativas

A API aceita apenas IDs presentes no catálogo; o navegador não fornece caminhos
de arquivos. Escritas exigem `PUT`, origem exata, token de sessão, JSON e tamanho
limitado. `Host` é verificado, CORS não é habilitado e o navegador recebe CSP.
Um microframework acrescentaria dependência sem benefício necessário neste
protótipo de usuário único; ele pode ser reconsiderado se a API crescer.

## Limites

O detector atual não persiste caixas alternativas para resultados inconclusivos.
Para Fairy Tail `s1`, o usuário deve desenhar uma região; as duas coordenadas
investigadas anteriormente não são incorporadas como hipóteses nem referência.
O agrupamento de sistemas permanece ambíguo e não há notas, ritmos, MusicXML,
importação de PDF ou edição musical. Corrigir no editor não altera o estado
`validated` de referências usadas em métricas. A interface exige revisão humana
de usabilidade antes de ser considerada aprovada.
