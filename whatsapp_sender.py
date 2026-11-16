import asyncio
import os
import re
from playwright.async_api import async_playwright
import config

WHATSAPP_PROFILE_DIR = os.path.join(os.path.dirname(__file__), "whatsapp_profile")


async def send_whatsapp_message(target_group, message_text):
    """Envia a mensagem para o grupo especificado usando a sessão salva."""
    print(f"Abrindo WhatsApp para enviar mensagem no grupo: '{target_group}'...")

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=WHATSAPP_PROFILE_DIR,
            headless=True,
            channel="chrome",
            args=["--no-sandbox", "--disable-notifications"]
        )

        page = browser.pages[0] if browser.pages else await browser.new_page()
        await page.goto("https://web.whatsapp.com")

        try:
            # 1. Aguarda a lista lateral de conversas carregar (#side)
            print("Carregando conversas do WhatsApp (#side)...")
            await page.wait_for_selector("#side", timeout=45000)
            await page.wait_for_timeout(3000)

            # 2. Localiza o campo de busca dentro de #side
            search_query = re.sub(r'[^\w\s-]', '', target_group).strip()
            print(f"Buscando por: '{search_query}'...")

            # Fecha popups/tooltips/dicas do WhatsApp que possam interceptar cliques
            await page.keyboard.press("Escape")
            await page.wait_for_timeout(500)

            search_box = page.locator('#side div[contenteditable="true"], #side [role="textbox"]').first
            try:
                await search_box.click(force=True, timeout=5000)
            except Exception:
                await search_box.focus()
            await page.wait_for_timeout(500)

            # Limpa qualquer texto anterior
            await page.keyboard.press("Control+A")
            await page.keyboard.press("Backspace")

            # Digita o nome do grupo na busca
            await search_box.fill(search_query)
            await page.wait_for_timeout(3000)

            # 3. Localiza e clica no grupo na lista de resultados
            # Procura por elementos dentro de #side que contenham o texto do grupo
            group_locator = page.locator(f'#side span[title*="{search_query}"], #side div[role="listitem"] span:has-text("{search_query}")').first
            if await group_locator.count() > 0:
                print(f"Grupo '{search_query}' encontrado na lista. Clicando...")
                await group_locator.click()
            else:
                print(f"Pressionando Enter no resultado da busca para '{search_query}'...")
                await page.keyboard.press("Enter")

            await page.wait_for_timeout(3000)

            # 4. Localiza a caixa de mensagem do chat ativo
            # O campo de texto do chat fica no footer ou fora de #side
            print("Localizando caixa de mensagem do chat...")
            msg_box = page.locator(
                'footer div[contenteditable="true"], div[data-tab="10"], div[data-tab="6"], #main div[contenteditable="true"]'
            ).last

            await msg_box.click()
            await page.wait_for_timeout(500)

            # 5. Digita a mensagem com quebras de linha (Shift+Enter)
            lines = message_text.split("\n")
            for i, line in enumerate(lines):
                if line:
                    await page.keyboard.type(line, delay=10)
                if i < len(lines) - 1:
                    await page.keyboard.down("Shift")
                    await page.keyboard.press("Enter")
                    await page.keyboard.up("Shift")

            await page.wait_for_timeout(1000)

            # 6. Envia a mensagem pressionando Enter
            await page.keyboard.press("Enter")
            await page.wait_for_timeout(4000)
            print(f"✅ Mensagem enviada com sucesso no grupo '{target_group}'!")
            return True

        except Exception as e:
            print(f"❌ Erro ao enviar mensagem no WhatsApp: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            await browser.close()


if __name__ == "__main__":
    test_msg = "🤖 *Teste de Integração do Robô Sigma Guilda*\nConexão com o WhatsApp realizada com sucesso no grupo Check-In G2 📆!"
    asyncio.run(send_whatsapp_message(config.WHATSAPP_GROUP_NAME, test_msg))
