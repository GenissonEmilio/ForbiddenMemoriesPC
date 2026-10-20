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
