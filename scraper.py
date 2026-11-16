import asyncio
from datetime import datetime, timedelta
import gspread
from playwright.async_api import async_playwright
import config

TARGET_SHEET_NAME = "g_doacoes"

def get_target_date_info():
    """Calcula a data D-1 (ontem)."""
    now = datetime.now()
    yesterday = now - timedelta(days=1)
    
    # Formato como aparece na tag <i>: DD/MM (ex: "08/11")
    game_date_str = yesterday.strftime("%d/%m")
    
    # Formato completo para salvar na planilha (ex: "08/11/2026")
    full_date_str = yesterday.strftime("%d/%m/%Y")
    
    return game_date_str, full_date_str

async def find_player_page(browser):
    """Encontra a aba correspondente ao Sigma Project."""
    for context in browser.contexts:
        for page in context.pages:
            try:
                title = await page.title()
                if "sigma" in title.lower() or "sigma" in page.url.lower():
                    return page
            except Exception:
                continue
    return None

async def navigate_to_treasury(page):
    """Navega pelos menus: Mundo -> Guilda -> REGISTRO -> tesouro."""
    print("Verificando estado atual da tela...")
    is_dossie_open = await page.evaluate('''() => {
        const aside = document.querySelector("aside.dossie");
        return aside && aside.offsetParent !== null;
    }''')
    
    if not is_dossie_open:
        print("1. Abrindo menu 'Mundo'...")
        mundo_btn = page.locator('button[title*="Mundo"]')
        if await mundo_btn.count() > 0:
            await mundo_btn.click()
            await page.wait_for_timeout(1000)
            
            print("2. Clicando em 'Guilda'...")
            await page.evaluate('''() => {
                const all = Array.from(document.querySelectorAll('*'));
                const g = all.find(el => el.innerText && el.innerText.trim().startsWith('Guilda') && el.tagName !== 'SPAN');
                if (g) g.click();
            }''')
            await page.wait_for_timeout(2000)

    # 3. Clicar em REGISTRO
    print("3. Clicando em REGISTRO no menu lateral da Guilda...")
    await page.evaluate('''() => {
        const btns = Array.from(document.querySelectorAll('aside.dossie nav button, aside.dossie button'));
        const reg = btns.find(b => b.innerText && b.innerText.toLowerCase().includes('registro'));
        if (reg) {
            reg.scrollIntoView();
            reg.click();
        }
    }''')
    await page.wait_for_timeout(1500)

    # 4. Clicar em tesouro
    print("4. Clicando na sub-aba 'tesouro'...")
    await page.evaluate('''() => {
        const btns = Array.from(document.querySelectorAll('aside.dossie button, aside.dossie div[role="tab"]'));
        const tes = btns.find(b => b.innerText && b.innerText.trim().toLowerCase() === 'tesouro');
        if (tes) {
            tes.click();
        }
    }''')
    await page.wait_for_timeout(1500)
    print("Aba de tesouro aberta com sucesso!")

async def scrape_treasury_records(page, target_d1_str, full_date_str):
    """
    Extrai EXATAMENTE todos os registros de doação de D-1 exibidos pelo jogo,
    preservando repetições legítimas (ex: mesmo jogador doando várias vezes no mesmo minuto).
    """
    print(f"Extraindo todas as doações para o dia D-1 ({target_d1_str})...")

    raw_records = await page.evaluate(r'''() => {
        const results = [];
        const iTags = document.querySelectorAll('aside.dossie i');
        for (const i of iTags) {
            const next = i.nextElementSibling;
            if (!next) continue;
            if (next.innerText && next.innerText.includes('doou')) {
                const iText = i.innerText.trim();
                const parts = iText.split(',');
                const d = parts[0] ? parts[0].trim() : '';
                const h = parts[1] ? parts[1].trim() : '';
                
                const bTags = Array.from(next.querySelectorAll('b')).map(b => b.innerText.trim());
                const player = bTags[0] || '';
                const valor = bTags[1] || '';
                
                results.push({ d, h, player, valor });
            }
        }
        return results;
    }''')

    filtered = []
    for item in raw_records:
        if item["d"] == target_d1_str:
            # Preserva cada linha individualmente, sem filtrar repetições de mesmo minuto
            filtered.append([full_date_str, item["h"], item["player"], item["valor"]])

    print(f"Total de registros de {target_d1_str} coletados: {len(filtered)}")
    return filtered

def save_to_google_sheets(records, target_date_str):
    """
    Anexa as doações na aba g_doacoes a partir da primeira linha em branco.
    Verifica se a data já foi inserida para evitar re-execuções duplicadas no mesmo dia.
    """
    if not records:
        print("Aviso: Nenhum registro de doação para salvar.")
        return

    print("Conectando ao Google Sheets...")
    gc = gspread.service_account(filename=config.CREDENTIALS_FILE)
    sh = gc.open_by_key(config.SPREADSHEET_ID)

    try:
        worksheet = sh.worksheet(TARGET_SHEET_NAME)
        print(f"Aba '{TARGET_SHEET_NAME}' encontrada.")
    except gspread.exceptions.WorksheetNotFound:
        print(f"Criando nova aba '{TARGET_SHEET_NAME}'...")
        worksheet = sh.add_worksheet(title=TARGET_SHEET_NAME, rows="1000", cols="10")

    existing_values = worksheet.get_all_values()
    header = ["data", "hora", "jogador", "doou"]

    # 1. Se a planilha estiver vazia, cria o cabeçalho
    if not existing_values:
        print("Adicionando linha de cabeçalho...")
        worksheet.append_row(header)
        existing_values = [header]
    elif existing_values[0] != header:
        # Se a primeira linha não for o cabeçalho, insere no topo
        worksheet.insert_row(header, index=1)
        existing_values.insert(0, header)

    # 2. Se já existirem dados dessa data específica (ex: 08/11/2026), removemos as linhas antigas
    # dessa data antes de re-inserir a lista completa e correta
    dates_in_sheet = [row[0] for row in existing_values[1:] if len(row) > 0]
    
    if target_date_str in dates_in_sheet:
        print(f"Dados da data {target_date_str} já existem na planilha. Atualizando a lista completa...")
        # Mantém apenas as linhas que NÃO são dessa data
        filtered_rows = [row for row in existing_values[1:] if len(row) > 0 and row[0] != target_date_str]
        all_to_write = [header] + filtered_rows + records
        worksheet.clear()
        worksheet.update(all_to_write, "A1")
        print(f"Sucesso! Planilha atualizada com todas as {len(records)} doações de {target_date_str}.")
    else:
        # Se for um dia novo, apenas anexa ao final a partir da primeira linha em branco
        worksheet.append_rows(records)
        print(f"Sucesso! {len(records)} novas linhas anexadas à aba '{TARGET_SHEET_NAME}'.")

async def close_guild_modal(page):
    """Fecha a janela da Guilda pressionando Escape para deixar a tela limpa."""
    await page.keyboard.press("Escape")

async def main():
    game_d1_str, full_date_str = get_target_date_info()
    print("=" * 60)
    print(f"Iniciando Coleta Sigma Project - LordCrypto")
    print(f"Data Alvo D-1: {game_d1_str} ({full_date_str}) | Destino: Aba '{TARGET_SHEET_NAME}'")
    print("=" * 60)

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(config.CDP_URL)
        except Exception as e:
            print(f"Erro ao conectar ao Chrome na porta {config.CDP_URL}: {e}")
            return

        page = await find_player_page(browser)
        if not page:
            print("Erro: Janela do Sigma Project não foi encontrada.")
            return

        print(f"Conectado com sucesso à janela: '{await page.title()}'")

        try:
            # 1. Navega até tesouro
            await navigate_to_treasury(page)

            # 2. Coleta os dados de ontem (todas as 17 ocorrências)
            records = await scrape_treasury_records(page, game_d1_str, full_date_str)

            # 3. Salva no Google Sheets
            save_to_google_sheets(records, full_date_str)

            # 4. Fecha a janela da guilda
            await close_guild_modal(page)
            print("=" * 60)
            print("Coleta finalizada com sucesso!")
            print("=" * 60)

        except Exception as e:
            print(f"Erro durante o processo: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
