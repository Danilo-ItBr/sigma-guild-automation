# 🤖 Sigma Guild Automation (RPA & Analytics)

Sistema completo e autônomo de **RPA (Robotic Process Automation)** e **Analytics** desenvolvido para o jogo *Sigma Project*. 

O robô automatiza o monitoramento diário da guilda: conecta-se ao navegador via **Chrome DevTools Protocol (CDP)**, extrai membros e registros contábeis do tesouro, sincroniza em tempo real com o **Google Sheets**, calcula a consolidação semanal por regras de negócio e despacha relatórios estruturados no **WhatsApp Web** sem custos de API.

---

## 🎯 Destaques de Engenharia e Tecnologias

- **Automação de Navegador Híbrida & Segura:** Uso de **Playwright** conectado via **CDP (Porta 9222)** a uma sessão já autenticada do jogo, evitando problemas com re-logins e tokens de autenticação.
- **Engenharia Reversa de DOM Dinâmico:** Extração resiliente em interface SPA/Canvas com seletores inteligentes, paginação e tratamento de elementos flutuantes/tooltips.
- **Sincronização em Nuvem (Google Sheets API):** Integração com `gspread` e conta de serviço (`credentials.json`), aplicando lógica de idempotência (elimina duplicatas de execuções no mesmo dia).
- **Consolidação Semanal & Lógica de Negócio:** Agrupamento por ciclo de guilda (Segunda 00:00 a Domingo 23:59), ranking de doações, cálculo de % de meta e detecção de inadimplência.
- **Despacho Automatizado no WhatsApp:** Automação em modo *headless* via WhatsApp Web com perfil persistente (`whatsapp_profile`), contornando pop-ups e enviando mensagens formatadas.
- **Arquitetura Modular:** Separação estrita de responsabilidades (Scraping, Consolidação, UX de Mensageria, Envio e Orquestração).

---

## 📁 Arquitetura do Projeto

```text
├── Abrir_Sigma_Robo.bat     # Inicia o Chrome com flags de depuração remota (CDP 9222)
├── Executar_Robo_Manual.bat # Execução manual sob demanda (fechamento D-1)
├── Executar_Robo_Hoje.bat   # Execução em tempo real (coleta D-1 + HOJE)
├── login_whatsapp.bat       # Script utilitário para autenticação inicial do QR Code
├── run.bat                  # Script de disparo agendado (Windows Task Scheduler)
│
├── config.example.py        # Template de configuração (variáveis de ambiente/IDs)
├── scraper.py               # Módulo de extração do tesouro (D-1)
├── members_scraper.py       # Módulo de extração da lista oficial de membros
├── consolidator.py          # Motor de cálculo e consolidação semanal
├── message_builder.py       # Formatador do relatório com emojis e status
├── whatsapp_sender.py       # Driver de automação de envio no WhatsApp Web
├── main.py                  # Orquestrador padrão da rotina diária
├── main_hoje.py             # Orquestrador em tempo real (inclui o dia de hoje)
│
├── requirements.txt         # Dependências do projeto
└── .gitignore               # Blindagem estrita contra vazamento de credenciais e sessões
```

---

## 📊 Fluxo de Funcionamento

```text
[Jogo Web (Chrome + CDP)]
         │
         ├───> [members_scraper.py] ───> [Google Sheets: g_membros]
         │
         └───> [scraper.py]         ───> [Google Sheets: g_doacoes]
                                                    │
                                                    ▼
                                          [consolidator.py]
                                                    │
                                                    ▼
                                         [message_builder.py]
                                                    │
                                                    ▼
                                        [whatsapp_sender.py]
                                                    │
                                                    ▼
                                        [Grupo no WhatsApp 📆]
```

---

## 🚀 Como Executar

### 1. Pré-requisitos
- **Python 3.10+**
- **Google Chrome** instalado
- Chave de Serviço do Google Cloud (`credentials.json`) com acesso ao Google Drive / Sheets API

### 2. Instalação
```bash
# Clone o repositório
git clone https://github.com/SEU_USUARIO/sigma-guild-automation.git
cd sigma-guild-automation

# Crie e ative o ambiente virtual
python -m venv .venv
.venv\Scripts\activate   # No Windows

# Instale as dependências
pip install -r requirements.txt
playwright install chromium
```

### 3. Configuração
1. Copie o arquivo `config.example.py` para `config.py`:
   ```bash
   copy config.example.py config.py
   ```
2. Abra `config.py` e insira o ID da sua planilha e o nome do seu grupo do WhatsApp.
3. Coloque seu arquivo `credentials.json` na raiz da pasta.

### 4. Execução
1. Abra o jogo utilizando o script:
   ```cmd
   Abrir_Sigma_Robo.bat
   ```
2. Para conectar o WhatsApp Web pela primeira vez (leitura de QR Code):
   ```cmd
   login_whatsapp.bat
   ```
3. Para rodar a rotina completa:
   ```cmd
   Executar_Robo_Manual.bat    # Coleta oficial D-1
   Executar_Robo_Hoje.bat      # Coleta em tempo real (inclui hoje)
   ```

---

## 🛡️ Segurança e Privacidade
Este projeto foi desenvolvido com rigor em segurança da informação:
- Todos os arquivos sensíveis de credenciais (`credentials.json`, `config.py`) e perfis de navegação com tokens e senhas (`chrome_profile/`, `whatsapp_profile/`) estão estritamente ignorados pelo `.gitignore`.
- O Chrome CDP roda em `127.0.0.1`, sem exposição de portas externas.

---

## 📄 Licença
Distribuído sob a licença MIT. Veja [LICENSE](LICENSE) para mais informações.
