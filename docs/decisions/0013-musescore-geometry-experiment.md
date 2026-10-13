# 0013 — MuseScore como ferramenta opcional de referências sintéticas

Em 2026-10-12, a auditoria encontrou MuseScore Studio 4.7.4 já instalado via
Flatpak de usuário (`org.musescore.MuseScore`, x86_64). A versão oficial mais
recente no site era 4.7.5, mas a instalada suportou todas as opções investigadas;
não instalamos uma segunda cópia nem adicionamos dependência ao projeto.

Uma referência MusicXML original de três notas foi importada e exportada como
PNG a 300/150 DPI, PDF, MSCZ, MusicXML, `mpos`, `spos` e JSON de
`--score-elements`. O PNG de 300 DPI mediu 2481×3507 px; `mpos` continha um
retângulo do compasso e `spos` três retângulos de segmentos na altura da pauta.
Dividir suas coordenadas por 48 produziu um overlay alinhado ao PNG de 300 DPI.
Em 150 DPI, a imagem mediu 1240×1754 px; a escala passa a cerca de 96 unidades
por pixel. O fator é evidência local desta versão, não contrato estável da CLI.

`--score-elements` descreveu E4, F4 e G4, suas durações e beat, índice de
compasso, pauta e voz. Não incluiu caixas geométricas das cabeças. O MusicXML
original e o reexportado conservaram os eventos suportados. O MusicXML de dois
compassos gerado pelo FluteOMR também foi importado e reexportado com os mesmos
eventos suportados. Isso não prova validade completa do esquema nem fidelidade
gráfica. Como a referência não declara instrumento, o MuseScore identificou a
parte como `grand-piano`; seu metadado instrumental não deve ser tratado como
ground truth de flauta.

Decisão: manter o MuseScore como ferramenta externa opcional de laboratório.
`mpos` pode ajudar com regiões de compassos e `spos` com tempos/segmentos após
normalização por DPI e verificação visual; nenhum fornece diretamente caixas
individuais de cabeças, hastes ou feixes. `--score-elements` pode cruzar eventos
da referência, sem substituir uma referência humana independente. Adiamos um
wrapper permanente até validar várias páginas, fontes e versões; o núcleo e os
testes padrão continuam independentes do MuseScore.
