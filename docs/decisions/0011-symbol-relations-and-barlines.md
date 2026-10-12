# 0011 — Relações mínimas e barras internas para múltiplos compassos

O detector da Sprint 1A classificava cabeças isoladamente e exigia limites de um
único compasso fornecidos pelo usuário. Em uma imagem externa de Twinkle, a
primeira pauta pequena produziu uma cabeça vazada espúria perto de uma semínima;
ampliar o recorte para espaçamento de 17 px preservou as sete notas esperadas,
mas ainda deixou uma duplicata vertical no mesmo `x`.

Adotamos uma supressão de duplicatas compatível com a voz monofônica atual e
estruturas pequenas para cabeças, hastes vinculadas e barras. A barra precisa
de tinta vertical cobrindo pelo menos 78% das linhas analisáveis entre as cinco
linhas, excluídas as faixas horizontais da pauta. Colunas largas ou próximas de
cabeças são rejeitadas. Barras próximas entre si causam erro explícito. O
algoritmo não consulta nome de arquivo, referência musical ou contagem esperada.

O modo multicompasso é opt-in; o modo de um compasso e o CLI legado permanecem.
Somente os limites externos, clave e fórmula são configuração. O MusicXML usa o
modelo existente e recusa compassos com duração inconclusiva ou desigual.
Guardamos IDs e regiões de origem para auditoria. O campo anterior
`boundary_origin` continua para compatibilidade; `boundary_origins` explicita a
origem de cada borda separadamente.

Alternativas descartadas agora: um grafo de símbolos genérico e binarização por
modelo de ML aumentariam custo e complexidade sem evidência de ganho. A
detecção atual não interpreta barras duplas/finais, não corrige perspectiva e
não prova completude de notas apenas pela soma rítmica. O recorte de Twinkle é
um teste exploratório externo, não referência humana validada. A etapa seguinte
precisa anotar notas e barras em imagens independentes para medir precisão,
recall e erro de associação.
