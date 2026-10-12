# 0008 — Anotador visual local com modelo independente

Estado: MVP implementado; abertura da janela depende do pacote opcional Tkinter.

O esquema versionado da Fase 5.1 continua sendo a fonte de verdade. O modelo
`annotation_editor.py` carrega e verifica hash/dimensões, edita uma cópia com
validação transacional, controla alterações pendentes e salva rascunhos
atomicamente. Referências validadas são somente leitura; a confirmação humana
permanece no comando `tools.evaluate_annotations confirm`. Excluir uma pauta
remove suas relações com sistemas e clave; região de sistema é derivada de seus
membros, sem novo campo no JSON.

`tools.annotate` apresenta a imagem em um canvas Tkinter, mas só mantém o trecho
visível como imagem Tk após o zoom. A imagem original permanece em coordenadas
inteiras; o zoom altera apenas a visualização. Um modo explícito de
movimentação/redimensionamento reduz edições acidentais. Listas e propriedades
permitem editar estados, caixa da clave, região e cinco linhas da pauta, membros
de sistemas e cobertura da página. Não há inferência automática de revisão.
Quando há um JSON de sugestões correspondente à mesma imagem, caixas de claves
aceitas aparecem tracejadas apenas como camada de consulta; candidatos
inconclusivos não têm caixas no formato atual de sugestões.

Tkinter integra a biblioteca padrão quando o pacote de sistema correspondente
está instalado. Ele não entra em `pyproject.toml` nem no CI headless. Alternativas
web/Electron adicionariam infraestrutura e custo para este fluxo local; editar
somente JSON continuaria pouco prático para corrigir geometria. A limitação do
MVP é não oferecer histórico de edições ou anotação de símbolos musicais além
da clave; testes do modelo não substituem uma verificação manual da janela em
um ambiente com Tkinter e display.
