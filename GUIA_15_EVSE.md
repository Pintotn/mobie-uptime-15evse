# Guia gratuito — 15 EVSE, recolha de 5 em 5 minutos

## Objetivo

Usar GitHub Actions para consultar o feed público MOBI.E a cada 5 minutos, guardar apenas 15 EVSE numa base PostgreSQL Neon Free e exportar relatórios CSV.

## Pré-requisitos

- Conta GitHub.
- Conta Neon.
- Repositório GitHub público.
- Os 15 identificadores UID das EVSE, exatamente como aparecem no feed DATEX II.

## 1. Criar o repositório GitHub

1. Entre em https://github.com.
2. Clique em **New repository**.
3. Nome sugerido: `mobie-uptime-15evse`.
4. Selecione **Public**.
5. Clique em **Create repository**.
6. Descompacte o ZIP deste projeto.
7. No repositório, clique em **Add file > Upload files**.
8. Carregue todo o conteúdo que está dentro da pasta `mobie_uptime_15evse`.
9. Confirme que `.github/workflows/collect-dynamic.yml` está visível.
10. Clique em **Commit changes**.

## 2. Criar a base Neon Free

1. Entre em https://console.neon.tech.
2. Crie uma conta gratuita.
3. Clique em **New project**.
4. Nome sugerido: `mobie-uptime`.
5. Escolha uma região europeia próxima.
6. Termine a criação do projeto.
7. Na página **Connection Details**, escolha **Pooled connection**.
8. Copie a connection string completa. Deve começar por `postgresql://` e o hostname costuma incluir `-pooler`.

Exemplo ilustrativo:

```text
postgresql://utilizador:password@ep-exemplo-pooler.eu-central-1.aws.neon.tech/neondb?sslmode=require
```

Não publique esta ligação.

## 3. Guardar a ligação como segredo no GitHub

1. No repositório, abra **Settings**.
2. Abra **Secrets and variables > Actions**.
3. No separador **Secrets**, clique em **New repository secret**.
4. Nome: `DATABASE_URL`.
5. Valor: cole a connection string do Neon.
6. Clique em **Add secret**.

## 4. Criar a lista das 15 EVSE

A lista deve usar os UIDs exatos do feed, separados por vírgulas e sem aspas.

Exemplo:

```text
PT*MOB*E00001,PT*MOB*E00002,PT*MOB*E00003
```

No GitHub:

1. Continue em **Settings > Secrets and variables > Actions**.
2. Abra o separador **Variables**.
3. Clique em **New repository variable**.
4. Nome: `EVSE_FILTER`.
5. Valor: cole os 15 UIDs separados por vírgulas.
6. Clique em **Add variable**.

Não use nomes comerciais ou números inventados: têm de ser os UIDs técnicos presentes no XML.

## 5. Permitir GitHub Actions

1. No repositório, abra **Settings > Actions > General**.
2. Em **Actions permissions**, deixe selecionado **Allow all actions and reusable workflows**.
3. Em **Workflow permissions**, a opção de leitura é suficiente.
4. Clique em **Save**.

## 6. Inicializar a base e obter os dados estáticos

1. Abra o separador **Actions** do repositório.
2. Na lista lateral, escolha **Atualizar cadastro e compactar dados**.
3. Clique em **Run workflow**.
4. Escolha a branch `main`.
5. Clique novamente em **Run workflow**.
6. Abra a execução e aguarde pelo visto verde.

Este workflow cria as tabelas e importa apenas as EVSE que correspondem à variável `EVSE_FILTER`.

## 7. Fazer a primeira recolha dinâmica

1. Ainda em **Actions**, escolha **Recolher estados MOBI.E**.
2. Clique em **Run workflow**.
3. Escolha `main` e confirme.
4. Abra a execução.
5. No passo **Recolher estados atuais**, procure uma mensagem semelhante a:

```text
Dados dinâmicos recolhidos: 15 estados.
```

Se aparecer `0 estados`, pelo menos um dos seguintes problemas existe:

- os UIDs não correspondem ao feed;
- a variável `EVSE_FILTER` contém espaços ou erros;
- o endpoint MOBI.E não respondeu;
- a ligação `DATABASE_URL` está incorreta.

## 8. Confirmar a recolha automática

O ficheiro `.github/workflows/collect-dynamic.yml` contém:

```yaml
schedule:
  - cron: "*/5 * * * *"
```

Isto pede uma execução de 5 em 5 minutos. O GitHub pode iniciar algumas execuções com atraso; não é uma garantia de relógio exato.

Depois de 15 a 30 minutos:

1. Abra **Actions > Recolher estados MOBI.E**.
2. Confirme que aparecem novas execuções automáticas.
3. Abra duas ou três e confirme que terminam com visto verde.

## 9. Exportar um relatório CSV

1. Abra **Actions**.
2. Escolha **Exportar relatório CSV**.
3. Clique em **Run workflow**.
4. Preencha, por exemplo:
   - `start`: `2026-07-01`
   - `end`: `2026-07-07`
   - `period`: `daily`
   - `group_by`: `evse`
5. Clique em **Run workflow**.
6. Quando terminar, abra a execução.
7. Na secção **Artifacts**, descarregue `uptime-daily-evse`.
8. Descompacte e abra o CSV no Excel.

Agrupamentos disponíveis:

- `network`: conjunto das 15 EVSE;
- `operator`: por operador;
- `city`: por cidade;
- `site`: por estação;
- `evse`: cada EVSE individualmente.

Períodos disponíveis:

- `daily`;
- `weekly`;
- `monthly`;
- `quarterly`;
- `semiannual`;
- `annual`.

## 10. Teste recomendado antes do mês oficial

Faça primeiro um teste de 24 horas:

1. Verifique se as execuções acontecem regularmente.
2. Confirme que cada execução lê 15 estados.
3. Exporte um relatório diário por EVSE.
4. Confirme que os UIDs e estados são os esperados.
5. Só depois defina o início oficial do estudo.

## 11. No fim do estudo

1. Exporte o relatório diário por EVSE.
2. Exporte o relatório mensal por EVSE.
3. Exporte também `network`, `operator` e `site`.
4. Guarde os ficheiros fora do GitHub.
5. Para parar as recolhas, abra `.github/workflows/collect-dynamic.yml` e remova/comente a secção `schedule`, ou desative o workflow em **Actions**.

## Diagnóstico rápido

### Erro de ligação à base

Confirme `Settings > Secrets and variables > Actions > Secrets > DATABASE_URL`.

### Recolha devolve zero

Revise `EVSE_FILTER`. Os 15 valores têm de coincidir exatamente com `record.uid` no feed.

### Workflow não aparece

Confirme que os ficheiros estão em `.github/workflows/` na branch `main`.

### Execuções não começam exatamente a cada cinco minutos

É normal haver atrasos no agendamento do GitHub Actions. A frequência é de melhor esforço.

### Repositório privado

Uma execução a cada cinco minutos consome demasiados minutos para a quota gratuita típica. Para esta configuração, mantenha o repositório público e nunca coloque passwords no código.
