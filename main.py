"""
main.py — Orquestrador Principal do Robô Sigma Guilda
======================================================
Executado diariamente às 09:00 pelo Windows Task Scheduler via run.bat.

Fluxo:
  1. Conecta ao Chrome via CDP (Chrome deve estar aberto com Abrir_Sigma_Robo.bat)
  2. Localiza a janela do Sigma Project
  3. Scrapa MEMBROS → salva em g_membros no Google Sheets
  4. Scrapa REGISTRO → tesouro (D-1) → salva em g_doacoes
  5. Fecha o painel da guilda (Escape)
  6. Consolida doações da semana atual
  7. Monta a mensagem de WhatsApp
  8. Envia para o grupo "Check-In G3 📆"
"""

import asyncio
from datetime import datetime, timedelta

from playwright.async_api import async_playwright

import config
from members_scraper import scrape_and_save_members
from consolidator import consolidate_weekly
from message_builder import build_weekly_message
from whatsapp_sender import send_whatsapp_message

# ── Re-usa as funções do scraper.py ──────────────────────────────────────────
from scraper import (
    get_target_date_info,
    find_player_page,
    navigate_to_treasury,
    scrape_treasury_records,
    save_to_google_sheets,
    close_guild_modal,
)


def _banner(titulo: str):
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"  {titulo}")
    print(f"{sep}")


async def main():
    agora = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    _banner(f"Robô Sigma Guilda — {agora}")

    # ── Passo 0: calcula data alvo D-1 ───────────────────────────────────────
    game_d1_str, full_date_str = get_target_date_info()
    print(f"Data alvo (D-1): {game_d1_str} → {full_date_str}")

    # ── Passo 1: conecta ao Chrome via CDP ───────────────────────────────────
    _banner("Passo 1/7 — Conectando ao Chrome")
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect_over_cdp(config.CDP_URL)
            print(f"✅ Conectado ao Chrome em {config.CDP_URL}")
        except Exception as e:
            print(f"❌ Falha ao conectar ao Chrome: {e}")
            print("   Certifique-se de que o Abrir_Sigma_Robo.bat foi executado antes.")
            return

        # ── Passo 2: localiza a página do jogo ───────────────────────────────
        page = await find_player_page(browser)
        if not page:
            print("❌ Janela do Sigma Project não encontrada. Abra o jogo primeiro.")
            return
        print(f"✅ Página encontrada: '{await page.title()}'")

        try:
            # ── Passo 3: scrapa MEMBROS ───────────────────────────────────────
            _banner("Passo 2/7 — Coletando lista de membros")
            members = await scrape_and_save_members(page)
            print(f"✅ {len(members)} membros salvos em 'g_membros'.")

            # ── Passo 4: scrapa REGISTRO → tesouro ───────────────────────────
            _banner("Passo 3/7 — Coletando doações do Tesouro (D-1)")
            await navigate_to_treasury(page)
            records = await scrape_treasury_records(page, game_d1_str, full_date_str)
            save_to_google_sheets(records, full_date_str)
            print(f"✅ {len(records)} doações de {full_date_str} salvas em 'g_doacoes'.")

            # ── Passo 5: fecha painel da guilda ───────────────────────────────
            _banner("Passo 4/7 — Fechando painel da Guilda")
            await close_guild_modal(page)
            print("✅ Painel fechado.")

        except Exception as e:
            print(f"❌ Erro durante coleta dos dados: {e}")
            import traceback
            traceback.print_exc()
            # Continua mesmo com erro de scraping para tentar enviar mensagem
            # com os dados que já estavam na planilha
            print("⚠️  Continuando com dados existentes na planilha...")

    # ── Passo 6: consolida semana ─────────────────────────────────────────────
    # (fora do bloco async_playwright pois usa apenas gspread)
    _banner("Passo 5/7 — Consolidando doações da semana")
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

    # ── Passo 7: monta mensagem ───────────────────────────────────────────────
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

    # ── Passo 8: envia WhatsApp ───────────────────────────────────────────────
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
