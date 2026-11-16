"""
coletar_historico.py — Script extraordinário para coleta histórica (05/11 até 13/11).
Não interfere no robô diário (main.py).
"""

import asyncio
from datetime import datetime, date
import gspread
from playwright.async_api import async_playwright
import config

TARGET_SHEET_NAME = "g_doacoes"

# Intervalo desejado: de 05/11/2026 até 13/11/2026
START_DATE = date(2026, 11, 5)
END_DATE = date(2026, 11, 13)


async def find_player_page(browser):
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
    print("Verificando estado do painel da Guilda...")
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

    print("3. Clicando em REGISTRO...")
    await page.evaluate('''() => {
        const btns = Array.from(document.querySelectorAll('aside.dossie nav button, aside.dossie button'));
        const reg = btns.find(b => b.innerText && b.innerText.toLowerCase().includes('registro'));
        if (reg) {
            reg.scrollIntoView();
            reg.click();
        }
    }''')
    await page.wait_for_timeout(1500)

    print("4. Clicando na sub-aba 'tesouro'...")
    await page.evaluate('''() => {
        const btns = Array.from(document.querySelectorAll('aside.dossie button, aside.dossie div[role="tab"]'));
        const tes = btns.find(b => b.innerText && b.innerText.trim().toLowerCase() === 'tesouro');
        if (tes) {
            tes.click();
        }
    }''')
    await page.wait_for_timeout(1500)
    print("Aba de tesouro aberta!")


async def scrape_range_records(page, start_date, end_date):
    """Extrai todas as doações do histórico entre start_date e end_date."""
    print(f"Extraindo doações no intervalo de {start_date.strftime('%d/%m/%Y')} até {end_date.strftime('%d/%m/%Y')}...")

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
    ano = 2026

    # O jogo mostra do mais recente ao mais antigo. Invertemos para gravar em ordem cronológica crescente.
    for item in reversed(raw_records):
        d_str = item["d"]  # Ex: "08/11"
        try:
            dia, mes = map(int, d_str.split('/'))
            reg_date = date(ano, mes, dia)
        except Exception:
            continue

        if start_date <= reg_date <= end_date:
            full_date_str = reg_date.strftime("%d/%m/%Y")
            filtered.append([full_date_str, item["h"], item["player"], item["valor"]])

    print(f"Total de registros filtrados no intervalo: {len(filtered)}")
    return filtered


def save_full_history_to_sheets(records):
    """
    Mantém o cabeçalho e preenche a aba g_doacoes com a lista completa do período.
    """
    print("Conectando ao Google Sheets...")
    gc = gspread.service_account(filename=config.CREDENTIALS_FILE)
    sh = gc.open_by_key(config.SPREADSHEET_ID)

    try:
        ws = sh.worksheet(TARGET_SHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        ws = sh.add_worksheet(title=TARGET_SHEET_NAME, rows="1000", cols="10")

    header = ["data", "hora", "jogador", "doou"]
    all_data = [header] + records

    print(f"Gravando {len(records)} doações na aba '{TARGET_SHEET_NAME}'...")
    ws.clear()
    ws.update(all_data, "A1")
    print(f"✅ Sucesso! Planilha atualizada com o histórico completo ({len(records)} registros).")


async def main():
    print("=" * 60)
    print("Iniciando Coleta Extraordinária de Histórico (05/11 a 13/11)")
    print("=" * 60)

    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(config.CDP_URL)
        except Exception as e:
            print(f"Erro ao conectar ao Chrome: {e}")
            return

        page = await find_player_page(browser)
        if not page:
            print("Página do jogo não encontrada.")
            return

        await navigate_to_treasury(page)
        records = await scrape_range_records(page, START_DATE, END_DATE)
        save_full_history_to_sheets(records)

        # Fecha o painel
        await page.keyboard.press("Escape")
        print("=" * 60)
        print("Coleta histórica concluída!")
        print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
