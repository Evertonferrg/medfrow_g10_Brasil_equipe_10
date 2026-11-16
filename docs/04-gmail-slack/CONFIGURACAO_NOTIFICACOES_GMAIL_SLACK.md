# Configuração de notificações --- Gmail e Slack

Este documento explica como obter e configurar as credenciais usadas
pelo módulo `app/notificacao.py` do MediFlow.

O MediFlow pode enviar alertas ao plantão por Slack, Gmail ou pelos dois
canais. As credenciais devem ficar somente no arquivo local `.env` e
nunca devem ser publicadas no GitHub.

## 1. Pré-requisitos

-   Acesso a uma conta Google que possa usar senhas de app.
-   Acesso a um workspace do Slack no qual você tenha permissão para
    instalar ou configurar aplicativos.
-   Projeto MediFlow instalado localmente.
-   Dependências do projeto instaladas no ambiente virtual.

Na raiz do projeto, confirme se existe um arquivo `.gitignore` e se ele
contém:

``` gitignore
.env
.env.*
!.env.example
```

Essa regra ignora arquivos locais de ambiente e permite manter um modelo
sem segredos chamado `.env.example`.

> **Importante:** não coloque senhas, tokens, URLs de webhook ou dados
> reais de pacientes em arquivos versionados, prints, mensagens ou
> exemplos de documentação.

## 2. Obter a senha de app do Gmail

O MediFlow utiliza SMTP do Gmail para enviar mensagens. Para autenticar,
use uma **senha de app**, e não a senha normal da sua conta Google.

### 2.1 Ativar a verificação em duas etapas

1.  Entre na sua Conta do Google: <https://myaccount.google.com/>.
2.  Abra **Segurança**.
3.  Na área de como você faz login no Google, selecione **Verificação em
    duas etapas**.
4.  Siga as instruções e conclua a ativação.

A opção de senha de app depende da política e das configurações da
conta. Ela pode não estar disponível em algumas contas de organização,
contas com proteção avançada ou outras configurações administradas.

### 2.2 Criar uma senha de app

1.  Abra a página de senhas de app:
    <https://myaccount.google.com/apppasswords>.
2.  Entre novamente, se o Google solicitar.
3.  Dê um nome que identifique o uso, por exemplo: `MediFlow`.
4.  Clique para criar a senha.
5.  Copie a senha gerada e guarde-a em um local seguro.

A senha de app é exibida pelo Google no momento da criação. Trate-a como
uma credencial secreta. Não a envie por e-mail ou chat e não a coloque
no código-fonte.

Se a página não permitir criar uma senha de app, verifique as políticas
da conta com o administrador ou consulte a ajuda oficial do Google:
<https://support.google.com/accounts/answer/185833>.

### 2.3 Dados necessários para o MediFlow

-   `GMAIL_USER`: endereço Gmail que fará o envio.
-   `GMAIL_APP_PASSWORD`: senha de app gerada no Google, não a senha
    normal da conta.
-   `PLANTAO_EMAIL_DESTINO`: endereço que receberá os alertas.

O código usa o servidor SMTP `smtp.gmail.com`, porta `587`, com
STARTTLS.

## 3. Criar um webhook de entrada no Slack

O Slack utiliza um **Incoming Webhook** para receber mensagens enviadas
pelo MediFlow em um canal.

### 3.1 Criar ou configurar o aplicativo

1.  Acesse <https://api.slack.com/apps>.
2.  Entre com a conta do workspace correto.
3.  Selecione **Create New App** e escolha a opção para criar do zero.
4.  Informe um nome, por exemplo `MediFlow Alertas`.
5.  Selecione o workspace em que o aplicativo será utilizado.
6.  Abra a configuração **Incoming Webhooks**.
7.  Ative a opção **Activate Incoming Webhooks**.
8.  Selecione **Add New Webhook to Workspace**.
9.  Escolha o canal que receberá os alertas.
10. Autorize a instalação, caso seja solicitada.

As opções e permissões disponíveis podem variar conforme as políticas do
workspace. Se não for possível instalar o aplicativo, solicite apoio ao
administrador do Slack.

### 3.2 Copiar a URL do webhook

Após autorizar, a página de Incoming Webhooks exibirá a URL criada para
o canal escolhido.

Copie a URL e guarde-a como segredo. Ela permite publicar mensagens no
canal associado. Não a publique no GitHub, em capturas de tela ou em
documentação.

Documentação oficial do Slack:
<https://api.slack.com/messaging/webhooks>.

### 3.3 Dado necessário para o MediFlow

-   `SLACK_WEBHOOK_URL`: URL completa do Incoming Webhook criado no
    Slack.

## 4. Configurar o arquivo `.env`

Na raiz do projeto MediFlow, crie ou edite o arquivo `.env`. Preencha
com os valores obtidos, sem aspas e sem espaços antes ou depois do sinal
de igualdade:

``` dotenv
# Canal de notificação: slack, email, ambos ou desativado
NOTIFICACAO_CANAL=ambos

# Slack Incoming Webhook
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/SEU/WEBHOOK/SEGREDO

# Gmail SMTP
GMAIL_USER=seu-email@gmail.com
GMAIL_APP_PASSWORD=SENHA_DE_APP_DO_GOOGLE
PLANTAO_EMAIL_DESTINO=email-do-plantao@exemplo.com

# URL base da interface (opcional)
UI_BASE_URL=http://localhost:8501
```

Substitua os valores de exemplo pelos seus próprios dados. A URL de
Slack acima é apenas ilustrativa; não é um webhook funcional.

### 4.1 Valores aceitos para `NOTIFICACAO_CANAL`

  -----------------------------------------------------------------------
  Valor                               Comportamento
  ----------------------------------- -----------------------------------
  `slack`                             Tenta enviar pelo Slack.

  `email`                             Tenta enviar pelo Gmail.

  `ambos`                             Tenta enviar por todos os canais
                                      que estiverem configurados.

  `desativado`                        Não envia notificações.
  -----------------------------------------------------------------------

Se um canal não tiver as credenciais necessárias, ele será ignorado. Se
nenhum canal selecionado estiver configurado, o serviço retorna
`desativado`.

`UI_BASE_URL` é opcional. Quando preenchida, o módulo pode incluir um
link para a interface no alerta. Confirme se a rota e o parâmetro de
consulta correspondem à versão atual do frontend.

## 5. Conferir a proteção das credenciais

Antes de fazer commit ou push, execute na raiz do repositório:

``` powershell
git check-ignore -v .env
```

O comando deve indicar que `.env` está sendo ignorado pelo `.gitignore`.

Confira também:

``` powershell
git status --short
```

O arquivo `.env` não deve aparecer como arquivo novo ou modificado a ser
enviado ao Git.

Se `.env` já tiver sido adicionado ao controle de versão anteriormente,
o `.gitignore` sozinho não o remove do rastreamento. Nesse caso,
remova-o do índice mantendo o arquivo local:

``` powershell
git rm --cached .env
```

Depois confira novamente o status. Se uma credencial real já foi
publicada, revogue ou gere outra credencial no serviço correspondente;
apagar o arquivo em um commit posterior não elimina o segredo do
histórico do Git.

## 6. Criar um modelo seguro `.env.example`

É útil manter um arquivo `.env.example` no repositório para mostrar
quais variáveis são necessárias, sem incluir valores secretos:

``` dotenv
NOTIFICACAO_CANAL=desativado

SLACK_WEBHOOK_URL=

GMAIL_USER=
GMAIL_APP_PASSWORD=
PLANTAO_EMAIL_DESTINO=

UI_BASE_URL=
```

Esse arquivo pode ser versionado. Cada pessoa da equipe deve criar seu
próprio `.env` local a partir do modelo e preencher as credenciais
individualmente.

## 7. Testar as notificações

### 7.1 Executar os testes automatizados

Com o ambiente virtual ativado, execute:

``` powershell
pytest -v testes/test_notificacao.py
```

Os testes automatizados do módulo usam objetos simulados para Slack e
SMTP. Eles validam o comportamento do código sem depender de uma entrega
real de mensagem.

Depois, execute toda a suíte:

``` powershell
pytest -q
```

### 7.2 Teste manual com envio real

Um teste manual que instancia `ServicoNotificacao()` e chama `enviar()`
pode disparar mensagens reais, conforme o valor de `NOTIFICACAO_CANAL` e
as credenciais presentes no `.env`.

Antes de executar qualquer script manual:

1.  Confirme que o canal está correto.
2.  Use um endereço e um canal de teste autorizados.
3.  Envie apenas uma mensagem de teste, sem dados de pacientes.
4.  Verifique a chegada da mensagem no destino.
5.  Não execute o teste manual em produção sem autorização.

**Atenção:** o arquivo `testar_notificacao.py`, se configurado para
chamar o serviço real, não é um teste isolado nem seguro para execução
automática. Não o inclua em rotinas de CI ou na suíte de testes sem
antes substituir as integrações reais por mocks.

## 8. Segurança e privacidade dos alertas

O MediFlow lida com informações potencialmente sensíveis. Slack, Gmail e
webhooks são canais externos; a equipe deve validar as políticas de
segurança, privacidade e acesso antes de utilizá-los com dados reais.

Boas práticas:

-   Envie somente o mínimo necessário para identificar e tratar o
    alerta.
-   Evite nome, CPF, diagnóstico detalhado, laudos, imagens e outros
    dados pessoais ou clínicos no corpo da mensagem.
-   Prefira um identificador interno do documento e um link para uma
    interface autenticada e com controle de acesso.
-   Restrinja o acesso ao canal do Slack e à caixa de e-mail do plantão.
-   Não use canais públicos para alertas operacionais.
-   Não registre senhas, tokens ou URLs completas de webhook nos logs.
-   Revogue e substitua imediatamente credenciais que tenham sido
    expostas.
-   Siga as regras internas de segurança e proteção de dados da
    instituição.

## 9. Resumo das variáveis

  -------------------------------------------------------------------------
  Variável                  Obrigatória para        Finalidade
  ------------------------- ----------------------- -----------------------
  `NOTIFICACAO_CANAL`       Definir o comportamento Seleciona Slack,
                                                    e-mail, ambos ou
                                                    desativado.

  `SLACK_WEBHOOK_URL`       Slack                   URL secreta do Incoming
                                                    Webhook.

  `GMAIL_USER`              Gmail                   Conta usada para
                                                    autenticar o envio.

  `GMAIL_APP_PASSWORD`      Gmail                   Senha de app do Google.

  `PLANTAO_EMAIL_DESTINO`   Gmail                   Destinatário dos
                                                    alertas.

  `UI_BASE_URL`             Opcional                Endereço base da
                                                    interface para compor o
                                                    link do alerta.
  -------------------------------------------------------------------------

------------------------------------------------------------------------

**Checklist de configuração**

-   [ ] Verificação em duas etapas ativada na conta Google.
-   [ ] Senha de app do Gmail criada.
-   [ ] Incoming Webhook criado no Slack.
-   [ ] Arquivo `.env` preenchido localmente.
-   [ ] `.env` ignorado pelo Git.
-   [ ] `.env.example` sem credenciais reais.
-   [ ] Testes automatizados executados.
-   [ ] Envio manual validado somente em canal e destinatário de teste.
-   [ ] Política de privacidade e acesso aos alertas revisada.
