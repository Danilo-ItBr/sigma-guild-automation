"""
main.py — Orquestrador Principal do Robô Sigma Guilda
======================================================
Executado diariamente às 09:00 pelo Windows Task Scheduler via run.bat
(ou manualmente via Executar_Robo_Manual.bat a qualquer hora).

Fluxo Inteligente com Auto-Start:
  1. Tenta conectar ao Chrome já aberto (porta 9222).
  2. SE o jogo estiver fechado:
     - Inicia automaticamente o Abrir_Sigma_Robo.bat.
     - Aguarda carregar a janela do jogo.
     - Fecha propagandas/anúncios/avisos iniciais (Esc / botões de fechar).
  3. Scrapa MEMBROS atuais -> salva/atualiza na aba 'g_membros'.
  4. Scrapa REGISTRO -> tesouro para Ontem (D-1) e HOJE (tempo real).
  5. Atualiza a aba 'g_doacoes' no Google Sheets com zero duplicidade.
  6. Fecha o painel da guilda (Escape).
  7. Consolida as doações (com fechamento inteligente na segunda-feira).
  8. Monta o relatório com destaques e alertas.
  9. Envia a mensagem formatada para o grupo do WhatsApp (Check-In G2 📆).
  10. Mantém o jogo aberto normalmente.
"""

import asyncio
import io
import os
import subprocess
import sys
from datetime import datetime, timedelta

# Garante saída UTF-8 no Windows para evitar erros de codificação em arquivos de log
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


def launch_game_if_closed():
    """Inicia o jogo via Abrir_Sigma_Robo.bat caso o Chrome não esteja aberto."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    bat_path = os.path.join(base_dir, "Abrir_Sigma_Robo.bat")
    print(f"🚀 O jogo estava fechado. Disparando inicialização automática: {bat_path}")
    try:
        subprocess.Popen(
            ["cmd.exe", "/c", bat_path],
            cwd=base_dir,
            creationflags=subprocess.CREATE_NEW_CONSOLE
        )
        return True
    except Exception as e:
        print(f"❌ Erro ao disparar o Abrir_Sigma_Robo.bat: {e}")
        return False


async def dismiss_initial_popups(page):
    """
    Fecha modais, avisos de novidades e propagandas que aparecem ao iniciar o jogo.
    Pressiona Escape repetidamente e tenta clicar em botões comuns de fechar.
    """
    print("🧹 Verificando e fechando propagandas/pop-ups iniciais...")
    await page.wait_for_timeout(3000)

    # 1. Pressiona Escape para fechar a maioria dos pop-ups nativos do jogo
    for _ in range(3):
        await page.keyboard.press("Escape")
        await page.wait_for_timeout(600)

    # 2. Varredura via JavaScript por botões típicos de fechar/entendi/x
    await page.evaluate('''() => {
        const closeSelectors = [
            'button[class*="fechar"]',
            'div[class*="fechar"]',
            'button[aria-label*="close" i]',
            'button[aria-label*="fechar" i]',
            'button.close',
            'span.close',
            'button:has-text("Fechar")',
            'button:has-text("Entendi")',
            'button:has-text("OK")'
        ];
        for (const sel of closeSelectors) {
            try {
                const elements = document.querySelectorAll(sel);
                for (const el of elements) {
                    if (el.offsetParent !== null) { // se estiver visível
                        el.click();
                    }
                }
            } catch (err) {}
        }
    }''')
    await page.wait_for_timeout(1000)

    # Pressiona Escape mais uma vez para garantir tela limpa
    await page.keyboard.press("Escape")
    print("✅ Tela do jogo limpa e pronta para o robô.")


async def scrape_donations_for_dates(page, target_dates):
    """
    Extrai doações que correspondam a qualquer uma das datas na lista target_dates.
    target_dates: lista de tuplas [(dd_mm_str, dd_mm_yyyy_str), ...]
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
    Substitui as linhas das datas alvos pelas novas, garantindo ZERO duplicidade.
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

    preserved_rows = [row for row in current_rows if len(row) > 0 and row[0] not in dates_to_update]

    new_rows = []
    for dt, recs in records_by_date.items():
        new_rows.extend(recs)

    all_to_write = [header] + preserved_rows + new_rows
    worksheet.clear()
    worksheet.update(all_to_write, "A1")
    print(f"✅ Planilha '{TARGET_SHEET_NAME}' atualizada com sucesso ({len(new_rows)} linhas sincronizadas).")


async def main():
    agora = datetime.now()
    ontem = agora - timedelta(days=1)

    hoje_game = agora.strftime("%d/%m")
    hoje_full = agora.strftime("%d/%m/%Y")

    ontem_game = ontem.strftime("%d/%m")
    ontem_full = ontem.strftime("%d/%m/%Y")

    _banner(f"Robô Sigma Guilda — {agora.strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"Datas alvos da extração: Ontem ({ontem_full}) e HOJE ({hoje_full}) até o momento")

    # ── Passo 1: Conecta ao Chrome via CDP (com Auto-Start se fechado) ────────
    _banner("Passo 1/7 — Conectando ao Chrome do Jogo")
    async with async_playwright() as p:
        browser = None
        game_was_closed = False

        # Primeira tentativa de conexão rápida
        try:
            browser = await p.chromium.connect_over_cdp(config.CDP_URL, timeout=4000)
            print(f"✅ Conectado ao jogo já aberto em {config.CDP_URL}")
        except Exception:
            print("⚠️ Jogo não está aberto ou não respondeu na porta 9222.")
            game_was_closed = True
            launch_game_if_closed()
            print("⏳ Aguardando 15 segundos para o jogo carregar completamente...")
            await asyncio.sleep(15)

            # Tenta conectar novamente após abrir
            for tentativa in range(1, 5):
                try:
                    browser = await p.chromium.connect_over_cdp(config.CDP_URL, timeout=5000)
                    print(f"✅ Conectado ao jogo com sucesso na tentativa {tentativa}/4!")
                    break
                except Exception as e:
                    print(f"   Aguardando porta 9222... (tentativa {tentativa}/4)")
                    await asyncio.sleep(5)

        if not browser:
            print("❌ Falha crítica: Não foi possível conectar ao jogo mesmo após iniciar.")
            return

        page = await find_player_page(browser)
        if not page:
            print("❌ Janela do Sigma Project não encontrada dentro do Chrome.")
            return
        print(f"✅ Página do jogo confirmada: '{await page.title()}'")

        # Se o jogo precisou ser aberto agora, limpa as propagandas iniciais
        if game_was_closed:
            await dismiss_initial_popups(page)

        try:
            # ── Passo 2: scrapa MEMBROS ───────────────────────────────────────
            _banner("Passo 2/7 — Coletando lista de membros atual")
            members = await scrape_and_save_members(page)
            print(f"✅ {len(members)} membros atualizados em 'g_membros'.")

            # ── Passo 3: scrapa REGISTRO -> tesouro (Ontem e Hoje) ────────────
            _banner("Passo 3/7 — Coletando doações do Tesouro (Ontem + Hoje)")
            await navigate_to_treasury(page)

            target_dates = [
                (ontem_game, ontem_full),
                (hoje_game, hoje_full)
            ]
            records_by_date = await scrape_donations_for_dates(page, target_dates)
            save_multiple_dates_to_sheets(records_by_date)

            # ── Passo 4: fecha painel da guilda (jogo permanece aberto!) ─────
            _banner("Passo 4/7 — Fechando painel da Guilda")
            await close_guild_modal(page)
            print("✅ Painel da guilda fechado (o jogo continua aberto na tela).")

        except Exception as e:
            print(f"❌ Erro durante coleta dos dados: {e}")
            import traceback
            traceback.print_exc()
            print("⚠️  Continuando com dados existentes na planilha...")

    # ── Passo 5: consolida semana ─────────────────────────────────────────────
    _banner("Passo 5/7 — Consolidando doações da semana")
    try:
        consolidation = consolidate_weekly()
        semana = consolidation["semana"]
        n_ok   = sum(1 for d in consolidation["membros"].values() if d["status"] == "ok")
        n_tot  = len(consolidation["membros"])
        print(f"✅ Consolidação ({consolidation['tipo_relatorio']}): {n_ok}/{n_tot} membros na meta.")
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
