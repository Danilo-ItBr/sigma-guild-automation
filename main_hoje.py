"""
main_hoje.py — Coleta até a data atual (Hoje) + Membros + Consolidação + WhatsApp
==================================================================================
Utilizado pelo Executar_Robo_Hoje.bat para coletar doações do dia de hoje (em tempo real),
além de D-1 (se ainda não coletado), consolidar a semana e enviar o relatório atualizado.
"""

import asyncio
import io
import sys
from datetime import datetime, timedelta

# Garante que emojis e caracteres especiais sejam gravados sem erro no log do Windows (cmd/batch)
if sys.stdout and hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
import gspread
from playwright.async_api import async_playwright

import config
from members_scraper import scrape_and_save_members
from consolidator import consolidate_weekly
from message_builder import build_weekly_message
from whatsapp_sender import send_whatsapp_message

from scraper import (
    find_player_page,
    navigate_to_treasury,
    close_guild_modal,
)

TARGET_SHEET_NAME = "g_doacoes"


def _banner(titulo: str):
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  {titulo}")
    print(f"{sep}")


async def scrape_donations_for_dates(page, target_dates):
    """
    Extrai doações que correspondam a qualquer uma das datas na lista target_dates.
    target_dates: lista de tuplas [(dd_mm_str, dd_mm_yyyy_str), ...]
    Ex: [("15/11", "15/11/2026"), ("14/11", "14/11/2026")]
    """
    date_map = {item[0]: item[1] for item in target_dates}
    target_game_strs = list(date_map.keys())

    print(f"Extraindo doações para as datas: {', '.join(target_game_strs)}...")

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

    # Separa os registros por data completa
    records_by_date = {full_dt: [] for full_dt in date_map.values()}

    for item in raw_records:
        d = item["d"]
        if d in date_map:
            full_dt = date_map[d]
            records_by_date[full_dt].append([full_dt, item["h"], item["player"], item["valor"]])

    for dt, recs in records_by_date.items():
        print(f"  • {dt}: {len(recs)} doações encontradas.")

    return records_by_date


def save_multiple_dates_to_sheets(records_by_date):
    """
    Atualiza atomicamente as datas coletadas na aba g_doacoes.
    Para cada data que teve registros, substitui as linhas antigas dessa data
    pelas novas, evitando duplicações mesmo se rodar várias vezes no mesmo dia.
    """
    gc = gspread.service_account(filename=config.CREDENTIALS_FILE)
    sh = gc.open_by_key(config.SPREADSHEET_ID)

    try:
        worksheet = sh.worksheet(TARGET_SHEET_NAME)
    except gspread.exceptions.WorksheetNotFound:
        worksheet = sh.add_worksheet(title=TARGET_SHEET_NAME, rows="1000", cols="10")

    existing_values = worksheet.get_all_values()
    header = ["data", "hora", "jogador", "doou"]

    if not existing_values:
        existing_values = [header]
    elif existing_values[0] != header:
        existing_values.insert(0, header)

    current_rows = existing_values[1:]
    dates_to_update = set(records_by_date.keys())

    # Remove linhas antigas das datas que estamos atualizando agora
    preserved_rows = [row for row in current_rows if len(row) > 0 and row[0] not in dates_to_update]

    new_rows = []
    for dt, recs in records_by_date.items():
        new_rows.extend(recs)

    all_to_write = [header] + preserved_rows + new_rows
    worksheet.clear()
    worksheet.update(all_to_write, "A1")
    print(f"✅ Planilha '{TARGET_SHEET_NAME}' atualizada com sucesso ({len(new_rows)} linhas inseridas/atualizadas).")


async def main():
    agora = datetime.now()
    ontem = agora - timedelta(days=1)

    hoje_game = agora.strftime("%d/%m")
    hoje_full = agora.strftime("%d/%m/%Y")

    ontem_game = ontem.strftime("%d/%m")
    ontem_full = ontem.strftime("%d/%m/%Y")

    _banner(f"Robô Sigma Guilda (COLETA ATÉ HOJE) — {agora.strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"Datas alvos: D-1 ({ontem_full}) e HOJE ({hoje_full})")

    # ── Passo 1: Conecta ao Chrome via CDP ───────────────────────────────────
    _banner("Passo 1/7 — Conectando ao Chrome")
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(config.CDP_URL)
            print(f"✅ Conectado ao Chrome em {config.CDP_URL}")
        except Exception as e:
            print(f"❌ Falha ao conectar ao Chrome: {e}")
            print("   Certifique-se de que o jogo está aberto com o Abrir_Sigma_Robo.bat.")
            return

        page = await find_player_page(browser)
        if not page:
            print("❌ Janela do Sigma Project não encontrada.")
            return
        print(f"✅ Página encontrada: '{await page.title()}'")

        try:
            # ── Passo 2: scrapa MEMBROS ───────────────────────────────────────
            _banner("Passo 2/7 — Coletando lista de membros atual")
            members = await scrape_and_save_members(page)
            print(f"✅ {len(members)} membros atualizados em 'g_membros'.")

            # ── Passo 3: scrapa REGISTRO → tesouro (D-1 e HOJE) ──────────────
            _banner("Passo 3/7 — Coletando doações (D-1 e HOJE)")
            await navigate_to_treasury(page)
            
            target_dates = [
                (ontem_game, ontem_full),
                (hoje_game, hoje_full)
            ]
            records_by_date = await scrape_donations_for_dates(page, target_dates)
            save_multiple_dates_to_sheets(records_by_date)

            # ── Passo 4: fecha painel da guilda ───────────────────────────────
            _banner("Passo 4/7 — Fechando painel da Guilda")
            await close_guild_modal(page)
            print("✅ Painel fechado.")

        except Exception as e:
            print(f"❌ Erro durante coleta dos dados: {e}")
            import traceback
            traceback.print_exc()
            print("⚠️  Continuando com dados existentes na planilha...")

    # ── Passo 5: consolida semana ─────────────────────────────────────────────
    _banner("Passo 5/7 — Consolidando doações da semana (incluindo HOJE)")
    try:
        consolidation = consolidate_weekly()
        semana = consolidation["semana"]
        n_ok   = sum(1 for d in consolidation["membros"].values() if d["status"] == "ok")
        n_tot  = len(consolidation["membros"])
        print(f"✅ Consolidação concluída: {n_ok}/{n_tot} membros na meta.")
        print(f"   Período: {semana['inicio'].strftime('%d/%m/%Y')} a {semana['fim'].strftime('%d/%m/%Y')}")
    except Exception as e:
        print(f"❌ Erro na consolidação: {e}")
        import traceback
        traceback.print_exc()
        return

    # ── Passo 6: monta mensagem ───────────────────────────────────────────────
    _banner("Passo 6/7 — Montando mensagem WhatsApp")
    try:
        mensagem = build_weekly_message(consolidation)
        print("✅ Mensagem montada:")
        print("-" * 40)
        print(mensagem)
        print("-" * 40)
    except Exception as e:
        print(f"❌ Erro ao montar mensagem: {e}")
        import traceback
        traceback.print_exc()
        return

    # ── Passo 7: envia WhatsApp ───────────────────────────────────────────────
    _banner("Passo 7/7 — Enviando mensagem no WhatsApp")
    try:
        sucesso = await send_whatsapp_message(config.WHATSAPP_GROUP_NAME, mensagem)
        if sucesso:
            print(f"✅ Mensagem enviada para '{config.WHATSAPP_GROUP_NAME}'!")
        else:
            print(f"❌ Falha ao enviar mensagem. Verifique os logs acima.")
    except Exception as e:
        print(f"❌ Erro ao enviar WhatsApp: {e}")
        import traceback
        traceback.print_exc()

    _banner(f"Robô finalizado — {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")


if __name__ == "__main__":
    asyncio.run(main())
