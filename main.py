import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import Modal, TextInput
from discord import TextStyle, Interaction
import os
import aiohttp
import asyncio
import json
import random
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv()

# Configuração das intents do Discord
intents = discord.Intents.all()
intents.message_content = True

# Configuração do bot
class Bot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents)
        
    async def setup_hook(self):
        await self.tree.sync()

bot = Bot()

# Lista de canais ativos (onde o bot responderá automaticamente)
canais_ativos = set()

# Configuração das APIs de IA
class IAClient:
    def __init__(self):
        self.hf_token = os.getenv('HF_TOKEN')
        self.openai_key = os.getenv('OPENAI_KEY')
        self.current_provider = 'huggingface'  # Padrão: huggingface
        
    async def query_huggingface(self, message):
        if not self.hf_token:
            print("Token do HuggingFace não configurado!")
            return None
        
        API_URL = "https://api-inference.huggingface.co/models/pierreguillou/gpt2-small-portuguese"
        headers = {"Authorization": f"Bearer {self.hf_token}"}
        
        async with aiohttp.ClientSession() as session:
            try:
                payload = {
                    "inputs": message,
                    "parameters": {
                        "max_length": 100,
                        "temperature": 0.7,
                        "top_p": 0.9,
                        "do_sample": True
                    }
                }
                
                async with session.post(API_URL, headers=headers, json=payload) as response:
                    if response.status == 200:
                        result = await response.json()
                        if isinstance(result, list) and len(result) > 0:
                            resposta = result[0].get('generated_text', '').replace(message, '').strip()
                            return resposta if resposta else None
                    elif response.status == 401:
                        print("Token do HuggingFace inválido!")
                    elif response.status == 503:
                        print("Modelo está carregando...")
                    else:
                        error = await response.text()
                        print(f"Erro HuggingFace: {response.status}")
            except Exception as e:
                print("Erro na conexão com HuggingFace")
            return None
    
    async def query_openai(self, message):
        if not self.openai_key:
            print("Chave da OpenAI não configurada!")
            return None
        
        try:
            import openai
            openai.api_key = self.openai_key
            
            response = openai.ChatCompletion.create(
                model="gpt-3.5-turbo",
                messages=[{"role": "user", "content": message}],
                max_tokens=100,
                temperature=0.7
            )
            return response.choices[0].message.content
        except ImportError:
            print("OpenAI não está instalado. Execute: pip install openai")
        except Exception as e:
            print("Erro OpenAI")
        return None
    
    async def query_ollama(self, message):
        try:
            async with aiohttp.ClientSession() as session:
                # Verifica se o Ollama está rodando
                try:
                    async with session.get("http://localhost:11434") as check_response:
                        if check_response.status != 200:
                            print("Ollama não está rodando ou não está acessível")
                            return None
                except:
                    print("Ollama não está disponível")
                    return None
                
                async with session.post(
                    "http://localhost:11434/api/generate",
                    json={
                        "model": "llama2",
                        "prompt": message,
                        "stream": False
                    }
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get("response")
        except Exception as e:
            print(f"Erro Ollama")
        return None
    
    async def get_response(self, message):
        # Ordem de tentativas: huggingface -> openai -> ollama -> fallback
        response = None
        
        if self.current_provider == 'huggingface' and self.hf_token:
            response = await self.query_huggingface(message)
            if response: return response
        
        if not response and self.openai_key:
            response = await self.query_openai(message)
            if response: return response
        
        if not response:
            response = await self.query_ollama(message)
            if response: return response
        
        # Fallback para respostas pré-definidas
        return random.choice([
            "Não consegui processar sua pergunta no momento.",
            "Poderia reformular sua pergunta?",
            "Estou com dificuldades técnicas...",
            "Interessante! O que mais gostaria de saber?",
            "No momento não consigo responder isso. Pergunte outra coisa!"
        ])

# Inicializa o cliente de IA
ia_client = IAClient()

@bot.event  
async def on_ready():
    print(f"Bot está online como {bot.user}")
    print("Comandos sincronizados com sucesso!")
    await bot.change_presence(activity=discord.Game(name="!ajuda para comandos"))

@bot.command(name="ajuda")
async def ajuda(ctx):
    comandos = """
**Comandos disponíveis:**
`!chat [mensagem]` - Conversa com o bot
`!ativar_canal` - Ativa o bot para responder mensagens neste canal
`!desativar_canal` - Desativa o bot neste canal
`!criar_canal [categoria] [canal]` - Cria um novo canal em uma categoria
`/criar_canal` - Abre um modal para criar canal (comando slash)
`!hello` - Teste se o bot está funcionando
`!trocar_ia [huggingface|openai|ollama]` - Muda o provedor de IA
`!limpar_chat [quantidade]` - Limpa o chat com a quantidade de mensagens especificada
`!limpar_chat_todos` - Limpa o chat com todas as mensagens

**Exemplo de uso:**
`!chat Olá, como vai você?`
`!criar_canal "Geral" "bate-papo"`
"""
    embed = discord.Embed(
        title="Ajuda do Bot",
        description=comandos,
        color=discord.Color.blue()
    )
    await ctx.reply(embed=embed)

@bot.command(name="chat")
async def chat_command(ctx, *, mensagem):
    async with ctx.typing():
        resposta = await ia_client.get_response(mensagem)
        await ctx.reply(resposta)

@bot.command(name="trocar_ia")
@commands.has_permissions(administrator=True)
async def trocar_ia(ctx, provider: str = None):
    if not provider:
        await ctx.reply("⚠️ Por favor, especifique o provedor de IA! Uso: `!trocar_ia [huggingface|openai|ollama]`")
        return
        
    provider = provider.lower()
    if provider in ['huggingface', 'openai', 'ollama']:
        # Verifica se as credenciais necessárias estão configuradas
        if provider == 'huggingface' and not ia_client.hf_token:
            await ctx.reply("⚠️ Token do HuggingFace não configurado! Adicione HF_TOKEN no arquivo .env")
            return
        elif provider == 'openai' and not ia_client.openai_key:
            await ctx.reply("⚠️ Chave da OpenAI não configurada! Adicione OPENAI_KEY no arquivo .env")
            return
            
        ia_client.current_provider = provider
        await ctx.reply(f"✅ Provedor de IA alterado para: {provider}")
    else:
        await ctx.reply("⚠️ Provedor inválido! Opções: huggingface, openai, ollama")

@bot.command(name="ativar_canal")
@commands.has_permissions(administrator=True)
async def ativar_canal(ctx):
    canal_id = ctx.channel.id
    if canal_id not in canais_ativos:
        canais_ativos.add(canal_id)
        await ctx.reply(f"✅ Bot ativado neste canal! Agora vou responder todas as mensagens aqui.")
    else:
        await ctx.reply("⚠️ O bot já está ativo neste canal!")

@bot.command(name="desativar_canal")
@commands.has_permissions(administrator=True)
async def desativar_canal(ctx):
    canal_id = ctx.channel.id
    if canal_id in canais_ativos:
        canais_ativos.remove(canal_id)
        await ctx.reply("✅ Bot desativado neste canal! Não vou mais responder automaticamente.")
    else:
        await ctx.reply("⚠️ O bot já está desativado neste canal!")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return
    
    await bot.process_commands(message)
    
    if message.channel.id in canais_ativos and not message.content.startswith('!'):
        async with message.channel.typing():
            resposta = await ia_client.get_response(message.content)
            await message.reply(resposta)

@bot.command()
async def hello(ctx):
    await ctx.reply("Olá! 👋 Como posso ajudar?")

# Modal personalizado para criar categoria e canal
class CanalModal(Modal, title="Criar Canal e Categoria"):
    def __init__(self):
        super().__init__(timeout=None)
        
    categoria = TextInput(
        label="Nome da categoria",
        placeholder="Ex: Projetos",
        required=True,
        style=TextStyle.short
    )
    
    canal = TextInput(
        label="Nome do canal de texto",
        placeholder="Ex: planejamento",
        required=True,
        style=TextStyle.short
    )

    async def on_submit(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        nome_categoria = self.categoria.value.strip()
        nome_canal = self.canal.value.strip()

        categoria = discord.utils.get(guild.categories, name=nome_categoria)
        if not categoria:
            categoria = await guild.create_category(nome_categoria)

        canal_existente = discord.utils.get(categoria.text_channels, name=nome_canal)
        if canal_existente:
            await interaction.followup.send(
                f"O canal **#{nome_canal}** já existe na categoria **{nome_categoria}**.",
                ephemeral=True
            )
        else:
            await guild.create_text_channel(nome_canal, category=categoria)
            await interaction.followup.send(
                f"Canal **#{nome_canal}** criado na categoria **{nome_categoria}** com sucesso!",
                ephemeral=True
            )

# Comando de slash que chama o modal
@bot.tree.command(name="criar_canal", description="Criar uma categoria e um canal de texto")
async def criar_canal_slash(interaction: discord.Interaction):
    modal = CanalModal()
    await interaction.response.send_modal(modal)

# Comando normal para criar canal
@bot.command(name="criar_canal")
@commands.has_permissions(administrator=True)
async def criar_canal_command(ctx, categoria: str, canal: str):
    guild = ctx.guild
    
    # Procura ou cria a categoria
    categoria_obj = discord.utils.get(guild.categories, name=categoria)
    if not categoria_obj:
        categoria_obj = await guild.create_category(categoria)
    
    # Verifica se o canal já existe
    canal_existente = discord.utils.get(categoria_obj.text_channels, name=canal)
    if canal_existente:
        await ctx.reply(f"O canal **#{canal}** já existe na categoria **{categoria}**.")
    else:
        await guild.create_text_channel(canal, category=categoria_obj)
        await ctx.reply(f"Canal **#{canal}** criado na categoria **{categoria}** com sucesso!")


@bot.command(name="limpar_chat")
@commands.has_permissions(administrator=True)
async def limpar_chat(ctx, quantidade: int = 10):
    if quantidade <= 0:
        await ctx.reply("⚠️ A quantidade de mensagens a limpar deve ser maior que 0.")
        return
    
    # Envia mensagem de confirmação primeiro
    mensagem = await ctx.send(f"🗑️ Limpando {quantidade} mensagens...")
    
    # Limpa as mensagens
    await ctx.channel.purge(limit=quantidade + 2)  # +2 para incluir o comando e a mensagem de confirmação
    
    # Envia nova mensagem informando que terminou (que não será deletada)
    await ctx.send(f"✅ Chat limpo com sucesso! {quantidade} mensagens foram removidas.", delete_after=5)

@bot.command(name="limpar_chat_todos")
@commands.has_permissions(administrator=True)
async def limpar_chat_todos(ctx):
    # Envia mensagem de confirmação primeiro
    mensagem = await ctx.send("🗑️ Limpando todas as mensagens...")
    
    # Limpa as mensagens
    await ctx.channel.purge()
    
    # Envia nova mensagem informando que terminou (que não será deletada)
    await ctx.send("✅ Chat limpo com sucesso! Todas as mensagens foram removidas.", delete_after=5)

# Inicia o bot
bot.run(os.getenv('DISCORD_TOKEN'))