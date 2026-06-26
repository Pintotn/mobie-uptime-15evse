# MOBI.E Uptime — instalação gratuita sem programas no PC

Esta versão usa apenas serviços acessíveis pelo navegador:

- **GitHub Actions**: executa a recolha automaticamente uma vez por hora;
- **Neon Free**: guarda os dados numa base PostgreSQL;
- **GitHub Actions**: cria relatórios CSV para descarregar;
- **Render Free (opcional)**: disponibiliza a API num endereço web.

Não é necessário instalar Python, Docker, Git ou PostgreSQL no computador.

## Limitações da modalidade gratuita

- A resolução padrão é de **uma hora**. Uma indisponibilidade que comece e termine entre duas recolhas pode não ser observada.
- As execuções agendadas do GitHub podem sofrer atrasos ocasionais.
- O detalhe por estação e EVSE é conservado durante 14 dias.
- Os resumos nacionais, por operador e por cidade são compactados diariamente e podem ser usados em relatórios semanais, mensais, trimestrais, semestrais e anuais.
- A base Neon Free tem capacidade limitada; consulte regularmente o consumo no painel Neon.
- Não existem backups automáticos completos nesta arquitetura gratuita. Exporte relatórios regularmente.

# Parte A — criar a base de dados Neon

1. Abra `https://neon.com` no navegador.
2. Crie uma conta gratuita.
3. Escolha **New Project**.
4. Dê um nome, por exemplo `mobie-uptime`.
5. Escolha uma região europeia quando estiver disponível.
6. Depois de criar o projeto, procure **Connection string**.
7. Se existir a opção, escolha a ligação **Pooled**.
8. Copie a ligação completa. O formato será semelhante a:

```text
postgresql://utilizador:password@servidor.neon.tech/base?sslmode=require
```

Guarde este valor de forma privada. Ele contém a password da base de dados.

# Parte B — carregar o projeto no GitHub

1. Crie um repositório GitHub **Private**.
2. No repositório, escolha **Add file → Upload files**.
3. Carregue todos os ficheiros e pastas desta pasta.
4. Confirme que a raiz do repositório contém:

```text
.github/
render.yaml
Dockerfile
pyproject.toml
README.md
GUIA_GRATUITO.md
src/
tests/
```

5. Clique em **Commit changes**.

# Parte C — guardar a ligação Neon no GitHub

1. Abra o repositório no GitHub.
2. Escolha **Settings**.
3. No menu lateral, escolha **Secrets and variables → Actions**.
4. Clique em **New repository secret**.
5. Nome do segredo:

```text
DATABASE_URL
```

6. No valor, cole a connection string copiada do Neon.
7. Clique em **Add secret**.

Nunca coloque a connection string num ficheiro do repositório.

# Parte D — fazer a primeira recolha

1. Abra o separador **Actions** do repositório.
2. Caso o GitHub peça autorização, clique em **I understand my workflows, go ahead and enable them**.
3. Abra o workflow **Atualizar cadastro e compactar dados**.
4. Clique em **Run workflow → Run workflow**.
5. Aguarde até aparecer um visto verde.
6. Abra o workflow **Recolher estados MOBI.E**.
7. Clique em **Run workflow → Run workflow**.
8. Confirme que termina com visto verde.

Depois disso, o workflow de estados será executado automaticamente uma vez por hora.

Para verificar uma execução:

1. Abra **Actions**.
2. Abra a execução mais recente.
3. Abra o passo **Recolher estados atuais**.
4. Procure uma mensagem semelhante a:

```text
Dados dinâmicos recolhidos: 12345 estados.
```

# Parte E — criar e descarregar um relatório CSV

1. Abra **Actions**.
2. Selecione **Exportar relatório CSV**.
3. Clique em **Run workflow**.
4. Preencha:

```text
start:      2026-07-01
end:        2026-07-31
period:     daily
Group by:   network
```

5. Clique em **Run workflow**.
6. Abra a execução quando estiver concluída.
7. Na secção **Artifacts**, clique no ficheiro `uptime-daily-network`.
8. Descompacte o ZIP descarregado e abra o CSV no Excel.

Períodos disponíveis:

```text
daily
weekly
monthly
quarterly
semiannual
annual
```

Agrupamentos:

```text
network    Portugal inteiro; histórico compacto
operator   por operador; histórico compacto
city       por cidade; histórico compacto
site       por estação; apenas detalhe recente
EVSE       por EVSE; apenas detalhe recente
```

O programa começa a criar histórico apenas após a primeira recolha. Não consegue reconstruir automaticamente meses anteriores.

# Parte F — API web gratuita no Render (opcional)

A API não é necessária para recolher dados nem para descarregar relatórios.

Para a ativar:

1. Abra o Render e escolha **New → Blueprint**.
2. Selecione este repositório.
3. Use a branch `main` e o caminho `render.yaml`.
4. O Render pedirá o valor de `DATABASE_URL`.
5. Cole a mesma connection string do Neon.
6. Aplique o Blueprint.

O endereço terá um formato semelhante a:

```text
https://mobie-uptime-api.onrender.com
```

Páginas úteis:

```text
/health
/docs
/v1/uptime
/v1/evses
```

No plano gratuito, o serviço web pode adormecer quando não é utilizado. O primeiro acesso depois de um período de inatividade pode demorar cerca de um minuto.

# Alterar a frequência

O ficheiro `.github/workflows/collect-dynamic.yml` contém:

```yaml
- cron: "17 * * * *"
```

Isto significa uma execução por hora, ao minuto 17.

Num repositório privado, não é recomendado reduzir muito o intervalo porque as execuções consomem a quota mensal gratuita do GitHub Actions. Num repositório público, os runners standard têm regras de faturação diferentes, mas o workflow agendado pode ser desativado após longos períodos sem atividade no repositório.

# Diagnóstico de erros

## Erro `DATABASE_URL is not set` ou ligação recusada

Confirme que criou o segredo exatamente com o nome:

```text
DATABASE_URL
```

Confirme também que copiou a ligação completa do Neon, incluindo `sslmode=require` quando fornecido.

## Erro no endpoint MOBI.E

Abra a execução do workflow e consulte a mensagem no último passo. Os erros mais comuns são timeout, DNS, código HTTP 403/404 ou alteração do XML.

## Relatório vazio

Pode significar que:

- as datas são anteriores à primeira recolha;
- a recolha ainda não terminou;
- não existem intervalos para o agrupamento pedido;
- pediu detalhe por estação/EVSE para uma data com mais de 14 dias.

Comece por criar um relatório `daily` e `network` para a data da primeira recolha.
