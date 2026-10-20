# Proveniência e escopo

Este projeto integra duas bases, sem tratar seus runtimes como intercambiáveis:

* Port nativo de Forbidden Memories: Unchiga/Yu-Gi-Oh-Forbidden-Memories-Recompiled,
  commit `2d3776e86d075fbbed0605f3c068de86eb0d1651`, de 20/10/2026.
  O código raiz, os sistemas do jogo e as regressões de gameplay vêm dessa base.
* Referência Tenkaichi 3: stufno102/Tenkaichi3Decomp,
  commit `81507cde58685a6f5aab917c298d9a9f82fe09b0`, sob `reference/tenkaichi3`.
  A licença dessa cópia está no próprio diretório.

As contribuições desta integração são o instalador e o importador de RAR/ZIP/BIN/IMG,
a validação repetível do disco e do jogo, as correções da referência web e a CI do fork.
Não se reivindica autoria das descompilações ou dos ports anteriores.

## Regressões web

`python3 -m unittest discover -s tests/integration -p test_web_reference.py -v`

* Alterar header, opções, compilador ou passe de transformação invalida o cache.
* Um build limpo gera os objetos dos dados antes da linkagem; falhas são propagadas.
* O linker reporta pré-requisitos ausentes de forma acionável.
* O script Cloudflare funciona em Linux e produz pedaços idênticos à imagem sintética.
* Com Emscripten instalado, compila C para LLVM IR, transforma as operações float,
  gera WebAssembly, executa com Node e verifica reutilização/invalidação do cache.

Esses testes não compilam nem distribuem dados de BT3. Uma compilação completa dessa
referência ainda precisa do disco do BT3. Não se publica nada no Cloudflare automaticamente.

## Validar o port nativo com seu disco

```sh
python3 tools/pc/validate_port.py --disc game/rpg-yfm.bin --binary tmp/pc/game32/memories-pc
```

Os testes usam diretórios de saves próprios, não os saves do jogador:

* Boot, menu, nome, introdução da história, primeiro duelo e primeira carta, duas vezes idênticas.
* Um duelo inteiro, incluindo resultado e retorno ao menu.
* Save state e retomada em outro processo, comparando 2.000 frames.

O relatório JSON registra o hash do executável e cada resultado. Isso valida esses fluxos;
não equivale a jogar toda a campanha ou testar todo hardware, áudio e controle físico.
Os relatórios e imagens ficam locais, em `tmp/validation/`, ignorado pelo Git.

## Dados do disco

O usuário fornece seu próprio disco americano SLUS-01411. A importação testa o SHA-256 do
executável contra `config/slus_01411/target.yaml`, exige os arquivos usados pelo runtime e
verifica que seus últimos setores existem. A imagem CloneCD pode ter outro hash do disco
de referência por diferenças nos setores RAW, mesmo quando o executável é idêntico.
Os arquivos `game/`, `tmp/`, ROMs, imagens RAW e arquivos RAR são ignorados pelo Git.

## Resultado local em 20/10/2026

O disco fornecido foi importado do RAR externo e do RAR interno, a partir da imagem
CloneCD `YUGIOH.img` (517.872.768 bytes). O executável SLUS_014.11 corresponde ao SHA-256
configurado. Os conteúdos do disco continuam apenas na máquina do usuário.

Validação executada:

* `python3 install.py --rom <RAR local>`: importação, build nativo Linux e suíte de gameplay concluídos.
* Primeiro duelo: duas execuções idênticas, LP 8000/8000, mão inicial
  410/302/107/231/573, primeira carta 410 jogada.
* Duelo completo contra Simon: resultados, recompensa e retorno ao Free Duel aprovados.
* Save/load no mapa: 2.000 frames idênticos após retomada em outro processo.
* Campanha inicial: Jono e três aldeões, avanço por Exit, revanche e flags persistentes aprovados.
* Quinze casos de screenshots da base: todos corresponderam aos hashes de referência.
* Janela nativa: inicialização OpenGL 4.6, captura da tela de título e saída normal.
* Ordenação LIBGS: limites, links e integridade da memória adjacente aprovados com o sysroot do jogo.
* Importador: cinco testes com dados sintéticos aprovados.
* Referência web: cinco testes aprovados no GitHub com Emscripten 6.0.0, incluindo WebAssembly real.

A primeira execução remota da suíte web está em
https://github.com/GenissonEmilio/ForbiddenMemoriesPC/actions/runs/39511904834 .
O relatório detalhado do instalador permanece local em `tmp/validation/verified-*/report.json`.

A compilação nativa completa, sem disco no runner, e os testes LIBGS/cache de mods/importação
passaram também em uma máquina limpa do GitHub:
https://github.com/GenissonEmilio/ForbiddenMemoriesPC/actions/runs/39511917553 .


## Launcher Linux 0.1.0

A interface GTK em português permite selecionar ou arrastar a ROM, validar/preparar
RAR/ZIP, lembrar o disco e abrir o port nativo. Inclui controles, acesso aos saves e
atalho no menu do Linux. Os arquivos do jogador ficam separados do pacote.

O release é construído em Ubuntu 22.04: interface x86-64 com Python/GTK/Cairo
incluídos e jogo i386 com loader e bibliotecas próprios. O leitor RAR é libarchive
3.8.10 verificado por SHA-256; a versão antiga da distribuição falhava no RAR
CloneCD fornecido. O diretório de recursos e o loader são preservados também quando
o jogo reinicia, e `buildid` acompanha as tabelas de símbolos para save states.

Verificação local do pacote:

* Janela sem ROM em container Ubuntu 22.04 sem Python, GTK, libarchive ou pacotes i386 instalados.
* RAR aninhado fornecido pelo usuário importado pelo executável congelado; jogo iniciou,
  renderizou 1.200 frames e a interface voltou ao estado pronto nesse mesmo container.
* Executável e runtime do pacote: primeiro duelo determinístico em duas execuções,
  duelo completo e replay de save/load de 2.000 frames aprovados.
* Reinício real ao sair dos créditos: o loader incluído reabriu o jogo, carregou seus
  mods e gerou o frame de título, com saída normal.
* Seis regressões do launcher e cinco do importador aprovadas; arquivo inválido
  preserva a seleção anterior e argumentos de arquivos são passados literalmente.

A CI `Linux desktop launcher` compila sem ROM e verifica a abertura da interface
nesse Linux limpo, em pushes para `main`/`web-port` e pull requests pertinentes.
O release contém os binários compilados, dependências, avisos e instruções em português;
a ROM e os relatórios com dados do jogo permanecem locais.
