
## Configuração recomendada para 15 EVSE

Consulte `GUIA_15_EVSE.md`. Esta versão suporta `EVSE_FILTER` e recolha GitHub Actions de 5 em 5 minutos.
# MOBI.E Uptime

> **Instalação gratuita sem programas no PC:** consulte [GUIA_GRATUITO.md](GUIA_GRATUITO.md). Esta modalidade usa GitHub Actions + Neon Free e disponibiliza relatórios CSV pelo navegador.

Programa Python para:

- recolher os feeds públicos DATEX II da MOBI.E;
- guardar o cadastro das EVSE e o histórico de estados por intervalos;
- tratar falhas do feed e EVSE ausentes como `UNKNOWN`, de forma configurável;
- calcular uptime diário, semanal, mensal, trimestral, semestral e anual;
- agregar por rede nacional, operador, cidade, estação ou EVSE;
- exportar CSV e disponibilizar uma API REST.

## 1. Fontes de dados

Por defeito, o projeto está configurado para os endpoints DATEX II publicamente referenciados:

```text
https://pgm.mobie.pt/integration/nap/evChargingInfra
https://pgm.mobie.pt/integration/nap/evActualStatus
```

O primeiro contém os dados estáticos e o segundo os estados atuais. Os URLs estão em variáveis de ambiente porque a MOBI.E não publica atualmente um contrato OpenAPI estável e pode alterar a infraestrutura.

O parser segue o mapeamento técnico oficial MOBI.E/EADME:

```text
Estático:
energyInfrastructureSite
  └─ energyInfrastructureStation
       └─ refillPoint[@xsi:type="ElectricChargingPoint"]

Dinâmico:
energyInfrastructureSiteStatus
  └─ energyInfrastructureStationStatus
       └─ refillPointStatus[@xsi:type="ElectricChargingPointStatus"]
            ├─ reference/@id
            └─ status
```

## 2. Cálculo

A unidade é a EVSE. Os estados são classificados assim:

| Classe | Estados principais |
|---|---|
| UP | `AVAILABLE`, `CHARGING`, `RESERVED`, `BLOCKED`, `OCCUPIED` |
| DOWN | `INOPERATIVE`, `OUTOFORDER`, `FAULTED`, `UNAVAILABLE`, `OFFLINE` |
| UNKNOWN | estado desconhecido, EVSE ausente ou lacuna prolongada do feed |
| EXCLUDED | `PLANNED`, `REMOVED` |

Indicador conservador:

```text
uptime = UP / (UP + DOWN + UNKNOWN)
```

O relatório devolve também:

```text
observed_uptime = UP / (UP + DOWN)
coverage = (UP + DOWN) / (UP + DOWN + UNKNOWN)
```

As percentagens semanais, mensais e restantes são calculadas somando segundos, nunca pela média simples das percentagens diárias.

## 3. Execução local com SQLite

```bash
python -m venv .venv
source .venv/bin/activate                    # Linux/macOS
# .venv\Scripts\activate                     # Windows
pip install -e ".[dev]"
cp .env.example .env
mobie-uptime init-db
mobie-uptime collect-static
mobie-uptime collect-dynamic
```

Para recolha contínua:

```bash
mobie-uptime scheduler
```

O feed dinâmico é consultado a cada 60 segundos e o estático uma vez por dia.

## 4. Docker e PostgreSQL

```bash
cp .env.example .env
docker compose up -d --build
```

Serviços:

- coletor contínuo;
- PostgreSQL;
- API em `http://localhost:8000`;
- documentação Swagger em `http://localhost:8000/docs`.

Verificar:

```bash
curl http://localhost:8000/health
```

## 5. Relatórios

Diário nacional:

```bash
mobie-uptime report \
  --start 2026-01-01 \
  --end 2026-01-31 \
  --period daily \
  --group-by network \
  --output reports/janeiro_diario.csv
```

Mensal por operador:

```bash
mobie-uptime report \
  --start 2026-01-01 \
  --end 2026-12-31 \
  --period monthly \
  --group-by operator \
  --output reports/operadores_mensal.csv
```

Outras granularidades:

```text
daily
weekly
monthly
quarterly
semiannual
annual
```

Outros agrupamentos:

```text
network
operator
city
site
evse
```

Filtrar uma EVSE:

```bash
mobie-uptime report \
  --start 2026-01-01 \
  --end 2026-06-30 \
  --period monthly \
  --evse-uid EVSE-001
```

## 6. API REST

Exemplo:

```bash
curl "http://localhost:8000/v1/uptime?start=2026-01-01&end=2026-12-31&period=monthly&group_by=network"
```

Por operador:

```bash
curl "http://localhost:8000/v1/uptime?start=2026-01-01&end=2026-12-31&period=monthly&group_by=operator"
```

Lista de EVSE:

```bash
curl "http://localhost:8000/v1/evses?limit=100"
```

## 7. Teste sem ligação à MOBI.E

O repositório inclui XML de exemplo:

```bash
mobie-uptime ingest-file static tests/fixtures/static_sample.xml
mobie-uptime ingest-file dynamic tests/fixtures/dynamic_sample_1.xml --observed-at 2026-01-01T00:00:00Z
mobie-uptime ingest-file dynamic tests/fixtures/dynamic_sample_2.xml --observed-at 2026-01-01T06:00:00Z
mobie-uptime ingest-file dynamic tests/fixtures/dynamic_sample_3.xml --observed-at 2026-01-01T09:00:00Z
```

Executar testes:

```bash
pytest -q
```

## 8. Regras de qualidade dos dados

- uma falha isolada de HTTP não altera imediatamente o estado das EVSE;
- após uma lacuna superior a `FEED_STALE_AFTER_SECONDS`, o período é marcado como `UNKNOWN`;
- numa fotografia completa, uma EVSE ausente em várias recolhas consecutivas é marcada como `UNKNOWN`;
- o payload estático pode ser guardado comprimido; o dinâmico fica desativado por defeito para evitar vários GB por dia;
- todos os tempos são guardados em UTC e os limites dos relatórios são construídos em `Europe/Lisbon`, incluindo dias de 23 e 25 horas.

## 9. Pontos a validar no primeiro feed real

A estrutura DATEX II está implementada de forma independente dos namespaces e segue os caminhos oficiais. Ainda assim, no primeiro acesso real deve confirmar:

1. os valores exatos do enum `status`;
2. se o feed dinâmico é uma fotografia completa ou apenas alterações;
3. a unidade de `availableChargingPower` e `maxPowerAtSocket`;
4. se o timestamp de publicação representa efetivamente o momento da mudança;
5. os limites de frequência e utilização aplicáveis ao endpoint.

## 10. Publicação no Render

O repositório inclui `render.yaml` na raiz. No Render:

1. escolha **New > Blueprint**;
2. ligue o repositório GitHub;
3. confirme que a branch selecionada é `main`;
4. mantenha o caminho do Blueprint como `render.yaml`;
5. aplique o Blueprint.

O Blueprint cria:

- `mobie-uptime-api`: serviço web para `/health`, `/docs`, `/v1/evses` e `/v1/uptime`;
- `mobie-uptime-collector`: worker contínuo que lê os feeds;
- `mobie-uptime-db`: PostgreSQL persistente.

A API usa o plano gratuito, mas o worker contínuo e a base de dados persistente usam planos pagos mínimos. Isto é necessário para manter a recolha ativa sem depender do computador do utilizador.

Depois do deploy, abra o endereço público do serviço `mobie-uptime-api` e acrescente:

```text
/health
/docs
```

Se o repositório tiver uma pasta adicional acima dos ficheiros, mova o conteúdo dessa pasta para a raiz. O Render tem de encontrar estes ficheiros diretamente na branch `main`:

```text
render.yaml
Dockerfile
pyproject.toml
src/
```