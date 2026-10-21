# Mouse no Linux desktop — 0.2.0

O adaptador nativo em `src/pc/platform/game_pointer.c` converte gestos em entradas
normais do controle. A lógica original mantém a legalidade das jogadas, fusões,
ataques, escolhas e mudanças de turno. O adaptador não altera cartas, LP, decks ou
regras para executar um gesto.

* A mão usa a posição dos objetos de carta existentes para hover, clique e arraste.
  O arraste acompanha uma captura da carta realmente exibida. Cinco destinos
  explícitos indicam as colunas; soltar fora deles cancela a jogada.
* Face para cima/baixo, coluna e estrela são escolhas separadas. Arrastar não
  escolhe uma estrela ou posição de defesa automaticamente.
* O campo tem uma faixa compacta com cinco colunas, da esquerda para a direita na
  visão do jogador, para selecionar monstro e alvo. Essa faixa permite navegar no
  campo sem depender de uma aproximação da câmera 3D.
* O menu inicial consulta a configuração, ordem, escala e posição dos itens. As
  escolhas de diálogo consultam a posição do destaque e a máscara de opções
  habilitadas. Clicar fora de uma escolha não confirma a seleção anterior.
* Saves e decks registram os retângulos durante o desenho; as áreas clicáveis
  acompanham escala, rolagem, layouts estreitos e confirmações de sobrescrita.
  Uma liberação isolada ou iniciada em outra tela não ativa uma opção.
* Uma barra de 44 pixels oferece voltar, confirmar, direções, detalhes/fusão e
  Start/fim do turno. Ela reserva espaço fora da imagem do jogo. Algumas telas
  originais ainda usam essas direções e OK, ou teclado/controle.

O suporte novo é para o executável Linux i386 incluído no pacote Linux x86-64.
Os demais backends continuam compilando com funções vazias. `MEMORIES_MOUSE=0`
desativa o adaptador para diagnóstico. Perda de foco, uso de teclado/controle,
menus do aplicativo e carregamento de estado cancelam gestos pendentes.

## Verificação

`tests/pc/pointer_targets_test.c` verifica down/up, arraste cancelado, troca de
tela durante um clique e botões diferentes do esquerdo. `save_menu_test.c` cobre
carregamento por clique usando o mesmo caminho de I/O real dos saves.
Esses testes usam dados sintéticos e não precisam de disco.

O teste local com disco usa a fila de eventos SDL real, em 4:3 e widescreen com
resolução interna 2x:

```sh
MEMORIES_DISC=/caminho/disco.bin python3 tools/pc/test_mouse_controls.py --binary /caminho/memories-pc
```

Ele verifica menu Options, arraste inválido, terceira carta na quarta coluna,
face aberta, segunda estrela guardiã, fim do turno e ataque ao monstro adversário.
Os resultados e capturas ficam em `tmp/mouse-controls/`. O driver SDL somente lê
seu arquivo de comandos quando `MEMORIES_SDL_SCRIPT_FILE` foi definido explicitamente.
Saves e configurações dos testes ficam em diretórios próprios.

`tools/pc/validate_port.py` complementa isso com boot, nome/história, primeiro
duelo determinístico em duas execuções, um duelo completo e replay de save/load
por 2.000 frames. A ROM e esses resultados locais não são enviados à CI.
