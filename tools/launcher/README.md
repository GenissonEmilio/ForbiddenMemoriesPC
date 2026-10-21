# Forbidden Memories PC — launcher Linux

Interface GTK 3 em português, com ilustração original feita em Cairo e estilos próprios.
O fluxo é escolher a ROM, prepará-la e iniciar o jogo. Há navegação por teclado, arrastar
e soltar arquivos, tela de controles, acesso aos saves e instalação de atalho no menu.
A janela pode ser redimensionada; o conteúdo permanece acessível por rolagem.

## Estado e processos

* `model.py`: seleção validada, preferências JSON atômicas, arquivos locais e processo do jogo.
* `main.py`: interface. Importação, validação e abertura do jogo rodam fora da thread GTK.
* `assets/`: CSS, emblema SVG e ícone PNG renderizado por `make_icon.py`.
* `release/`: compilação em Ubuntu 22.04, freezer PyInstaller e empacotamento portátil.

Configuração e ROMs extraídas ficam em `$XDG_DATA_HOME/ForbiddenMemoriesPC` ou
`~/.local/share/ForbiddenMemoriesPC`. Os saves ficam em `player/saves` nesse diretório.
BIN/IMG são lidos no local original; arquivos RAR/ZIP ganham uma cópia gerenciada.
Escolher um arquivo inválido preserva a seleção anterior. O jogo valida o executável
SLUS-01411 novamente antes de cada abertura. Arquivos fornecidos pelo usuário não são executados.

O launcher é x86-64; o jogo da base é i386. O pacote contém um loader e bibliotecas i386
isolados, incluindo fallback Mesa. A interface não transmite suas bibliotecas GTK de
64 bits ao jogo. Não há compilação nem download durante a execução do release.
O executável do jogo foi compilado previamente a partir da descompilação existente:
a ROM fornece os dados que ele precisa; não se descompila um jogo arbitrário em tempo real.

## Desenvolvimento

O launcher-fonte requer Python, PyGObject, GTK 3 e pycairo. `libarchive` é necessário
apenas para importar RAR. O release empacota essas dependências.

```sh
python3 tools/launcher/main.py
python3 -m unittest discover -s tests/pc -p test_launcher_model.py -v
sh tools/launcher/release/build-linux.sh
```

A geração do release não necessita de ROM. Os testes de interface podem capturar uma
janela sem abrir o jogo, usando `--data-dir <pasta-temporária> --screenshot <png>`.
Um teste local completo usa `--rom <arquivo> --test-game --screenshot <png>`: prepara a
ROM, aciona a abertura pelo mesmo código do botão, espera 1.200 frames, captura a interface
e registra `launcher-test.json`. Isso não altera os saves do usuário quando uma pasta
temporária própria é passada com `--data-dir`.

O build inclui os avisos das bibliotecas de distribuição em `licenses/`, o inventário
dos pacotes Debian do runtime e as licenças do port e do launcher. O código e as receitas
de compilação são publicados junto ao release no repositório.
