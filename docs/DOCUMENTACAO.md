# Documentação — k230_updater

Biblioteca MicroPython para CanMV K230 com:

1. Atualização remota a partir de um repositório GitHub **privado** (programa `main` e modelos `.kmodel`).
2. Salva-guarda com **watchdog de hardware**, rollback automático e atualização corretiva.
3. **Controle térmico** que reduz FPS de captura para respeitar uma temperatura máxima.

> Status: escrita sem teste em hardware. Valide `WDT`, `requests`/HTTPS e a leitura de temperatura no seu firmware.

---

## 1. Instalação

Cartão SD:

```
/sdcard/main.py            launcher permanente (main.py da raiz deste repositório)
/sdcard/config.json        copie de config.example.json e preencha
/sdcard/k230_updater/      pasta da biblioteca
/sdcard/app/               criada automaticamente
    current/               versão em execução
    previous/              versão anterior (alvo do rollback)
    staging/               download temporário
    state.json             estado do salva-guarda
```

`config.json`:

| Campo | Padrão | Descrição |
|---|---|---|
| `repo` | — | `"dono/repositorio"` privado |
| `token` | — | PAT *fine-grained* com permissão **Contents: Read-only** apenas nesse repositório |
| `branch` | `main` | Branch lida |
| `update_url` | — | Se definido, usa a fonte HTTP/zip (seção 2b) em vez do GitHub |
| `report_url` | — | URL do POST do exemplo de segmentação |
| `wdt_timeout` | `10` | Timeout do watchdog (s) |
| `max_fails` | `3` | Falhas antes de proibir a versão e voltar |
| `confirm_after` | `60` | Segundos alimentando o WDT para considerar a versão boa |

Edite `connect()` em `main.py` para o seu meio de rede (Ethernet/Wi-Fi). **Não versione o `config.json`** (contém o token).

## 2. Repositório privado (o que é baixado)

Estrutura:

```
manifest.json
main.py
models/detector.kmodel
```

`manifest.json`:

```json
{
  "version": "1.0.1",
  "entry": "main.py",
  "files": [
    {"path": "main.py", "sha256": "<hex>"},
    {"path": "models/detector.kmodel", "sha256": "<hex>"}
  ]
}
```

- `version`: string comparada por igualdade; **mude a cada release**.
- `entry`: arquivo executado (padrão `main.py`).
- `files[].sha256`: opcional mas recomendado; se divergir, a instalação é abortada.
- Gerar hash: `python -c "import hashlib,sys;print(hashlib.sha256(open(sys.argv[1],'rb').read()).hexdigest())" arquivo`

O app baixado executa com `cwd` e `sys.path` em `/sdcard/app/current`, então `models/detector.kmodel` é aberto por caminho relativo. Veja `examples/app_main.py`.

## 2b. Fonte de atualização HTTP (zip)

Alternativa ao GitHub: defina `"update_url"` no `config.json` (ou `Guard(..., update_url=...)`). A cada boot a placa faz:

```
GET <update_url>?chipid=<id hex do K230>&last_update=<data da última atualização>
```

- `last_update`: campo `updated_at` do manifesto instalado (vazio se nada instalado).
- Resposta `204`/`304`: sem novidade. `200`: corpo é um **zip** com `main.py`, `models/*.kmodel` etc.
- Versão: `manifest.json` dentro do zip (opcional) ou cabeçalho `X-Version`; data: `updated_at` do manifesto ou cabeçalho `X-Updated-At` (senão, hora local da placa). Se nada definir a versão, a atualização falha.
- Se `token` estiver no config, é enviado como `Authorization: Bearer`.
- Versões proibidas pelo salva-guarda são descartadas após o download.
- Zip: use **sem compressão** (`zip -0`) para modelos grandes (extração em blocos); entradas deflate são lidas inteiras na RAM e exigem `deflate`/`zlib`/`uzlib` no firmware. Caminhos com `..` ou absolutos são rejeitados.
- O chip id vem de `machine.chipid()` (`k230_updater.device.chip_id()`); confira no seu firmware.

Servidor de referência (PC): `python examples/server.py` (GET `/update`, POST `/report`).

## 2c. Exemplo completo: segmentação + relatório

`examples/segmentation_app/main.py` (copie para o pacote junto com `models/yolov8n_seg.kmodel`): captura da câmera, inferência YOLOv8-seg com `nncase_runtime`, NMS, contagem de objetos e área de máscara, FPS controlado por `Thermal`, e `POST` a cada `REPORT_EVERY_S` segundos para `report_url`:

```json
{"chipid": "...", "objects": 3, "temp": 61.5, "mask_pixels": 1234}
```

É um modelo de partida **não testado**: ajuste tamanho de entrada, classes, normalização e chamadas de mídia ao seu modelo/firmware.

## 3. Fluxo de boot e salva-guarda

```
boot() ─ inicia WDT
   ├─ estado "trial"? (última execução não foi confirmada) → conta falha
   │     └─ fails ≥ max_fails → versão vai para "bad", rollback p/ previous
   ├─ try_update(): instala versão nova se existir e não estiver em "bad"
   ├─ sem versão executável? aguarda e tenta atualizar a cada retry_interval
   └─ marca "trial" e executa o entry
        ├─ app alimenta o WDT por confirm_after s → confirm() (status ok, fails=0)
        ├─ exceção não tratada → fails+1 e reset
        └─ travou → WDT estoura → reset → volta ao topo
```

Atualização corretiva: uma versão proibida nunca é reinstalada, mas **qualquer versão com número diferente** é. Publicar `1.0.2` corrige um `1.0.1` defeituoso mesmo que a placa esteja em loop de reset (a atualização ocorre antes de rodar o app).

Garantias de integridade: download em `staging` com SHA-256, troca por renomeação; falha no download não afeta `current`. O JSON de estado é gravado via arquivo temporário.

Limitações: se o launcher ou a biblioteca tiverem bug, não há recuperação remota — mantenha-os mínimos. Se não houver rede e a versão atual estiver proibida, a placa espera sem rodar app.

## 4. Controle térmico

```python
gov = Thermal(max_temp=75, target_fps=30, min_fps=2, feed=guard.feed)
while True:
    img = sensor.snapshot()
    ...                 # inferência
    gov.pace()          # mantém FPS, adapta à temperatura, alimenta o WDT
```

Comportamento (checado a cada `interval_ms`):

| Temperatura | Ação |
|---|---|
| ≥ `max_temp + critical_margin` | nível 2: pausa captura (alimentando o WDT) até ≤ `max_temp - hysteresis` |
| ≥ `max_temp` | FPS × 0,7 (mínimo `min_fps`), nível 1 |
| ≤ `max_temp - hysteresis` | FPS × 1,15 até `target_fps`, nível 0 |
| entre os dois | mantém |

Parâmetros: `max_temp`, `target_fps`, `min_fps=1`, `hysteresis=3`, `critical_margin=5`, `interval_ms=2000`, `read=None`, `feed=None`, `on_throttle=None`.

- `read`: função que devolve °C. Se omitida, tenta `machine.temperature` e `machine.TSENSOR`; se falhar, levanta `RuntimeError`.
- `on_throttle(level)`: chamado quando o nível muda (0 normal, 1 reduzido, 2 pausado). Use para reduzir clock de CPU/KPU ou desligar periféricos — a biblioteca não altera frequências por conta própria.

## 5. Referência da API

### `Guard(repo, token, root="/sdcard/app", branch="main", wdt_timeout=10, wdt_id=1, max_fails=3, confirm_after=60, retry_interval=60, connect=None)`

| Método | Descrição |
|---|---|
| `boot()` | Fluxo completo descrito na seção 3; não retorna normalmente |
| `feed()` | Alimenta o WDT e confirma a versão após `confirm_after` s |
| `confirm()` | Confirma a versão atual manualmente |
| `try_update()` | Verifica/instala atualização; nunca levanta exceção; retorna versão instalada ou `None` |
| `update_and_reset()` | `try_update()` e reinicia se instalou algo |
| `reset()` | `machine.reset()` |
| `start_wdt()` / `stop_wdt()` | Controle do watchdog |

Dentro do app: `import k230_updater; guard = k230_updater.guard`.

### `Updater(repo, token, root, branch, feed)`

`remote_manifest()`, `local_manifest()`, `install(manifest)`, `check_and_install(skip_versions=())`, `rollback()`. Levanta `UpdateError` em HTTP ≠ 200, manifesto inválido ou hash divergente.

### `Thermal`

`pace()`, `update()`; atributos `fps`, `temp`, `level`.

## 6. Boas práticas e segurança

- Token somente leitura, restrito a um repositório; rotacione periodicamente.
- Sempre inclua `sha256` no manifesto.
- Chame `guard.feed()` (ou `pace()`) em todo laço longo; carregar modelo grande pode exceder `wdt_timeout` — aumente-o ou alimente durante o carregamento.
- Teste cada release em uma placa antes de publicar na branch lida pelas demais; considere usar uma branch `stable`.
- Para depurar via IDE, interrompa o app (Ctrl+C): o WDT é parado e o estado volta a `ok`.

## 7. Solução de problemas

| Sintoma | Causa provável |
|---|---|
| `GET ... -> HTTP 404` | caminho/branch errado ou token sem acesso |
| `HTTP 401/403` | token inválido, expirado ou sem *Contents: Read* |
| `sha256 mismatch` | hash do manifesto desatualizado |
| Reinícios constantes | app não alimenta o WDT; aumente `wdt_timeout` |
| `no temperature sensor found` | passe `read=` |
| Placa parada sem app | versão atual proibida e sem rede/nova versão |
