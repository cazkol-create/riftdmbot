# main.py
import os
import json
import random
import re
import nextcord
import requests
from nextcord.ext import commands
from dotenv import load_dotenv
from datetime import datetime
from nextcord.ui import View, Button, Modal, TextInput
from nextcord import Interaction, TextInputStyle, ButtonStyle

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

intents = nextcord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

characters = {}
party_members = []
current_turn = 0
status_effects = {}
player_stats = {}

def roll_formula(formula):
    match = re.match(r"(\d+)d(\d+)([+-]\d+)?", formula)
    if not match:
        return 0
    num_dice = int(match[1])
    die_size = int(match[2])
    modifier = int(match[3]) if match[3] else 0
    rolls = [random.randint(1, die_size) for _ in range(num_dice)]
    return sum(rolls) + modifier

@bot.event
async def on_ready():
    print(f"✅ Rift DM is online as {bot.user}!")

    for guild in bot.guilds:
        log_channel = nextcord.utils.get(guild.text_channels, name="logs")
        if not log_channel:
            continue

        async for msg in log_channel.history(limit=200, oldest_first=True):
            if msg.author == bot.user and msg.content.startswith("[CHARACTER LOG]"):
                try:
                    lines = msg.content.splitlines()
                    user_id = lines[1].split("UserID: ")[1].strip()
                    name = lines[2].split("Name: ")[1].strip()
                    race = lines[3].split("Race: ")[1].strip()
                    char_class = lines[4].split("Class: ")[1].strip()
                    stats = json.loads(lines[5].split("Stats: ")[1].strip())
                    passives = json.loads(lines[6].split("Passives: ")[1].strip())
                    personality = lines[7].split("Personality: ")[1].strip()
                    characters[user_id] = {
                        "name": name,
                        "race": race,
                        "class": char_class,
                        "stats": stats,
                        "passives": passives,
                        "personality": personality,
                        "inventory": []
                    }
                except Exception as e:
                    print(f"⚠️ Failed to load character from log: {e}")

class CreateCharModal(Modal):
    def __init__(self):
        super().__init__("Create Your Character")
        self.name = TextInput(label="Name")
        self.race = TextInput(label="Race")
        self.char_class = TextInput(label="Class")
        self.personality = TextInput(label="Personality", style=TextInputStyle.paragraph)

        self.add_item(self.name)
        self.add_item(self.race)
        self.add_item(self.char_class)
        self.add_item(self.personality)

    async def callback(self, interaction: Interaction):
        user_id = str(interaction.user.id)
        characters[user_id] = {
            "name": self.name.value,
            "race": self.race.value,
            "class": self.char_class.value,
            "stats": {
                "strength": 10,
                "dexterity": 10,
                "intelligence": 10
            },
            "passives": [],
            "personality": self.personality.value,
            "inventory": []
        }
        await interaction.response.send_message(f"✅ Character `{self.name.value}` created!", ephemeral=True)

        log_channel = nextcord.utils.get(interaction.guild.text_channels, name="logs")
        if log_channel:
            await log_channel.send(
                "[CHARACTER LOG]\n"
                f"UserID: {user_id}\n"
                f"Name: {self.name.value}\n"
                f"Race: {self.race.value}\n"
                f"Class: {self.char_class.value}\n"
                f"Stats: {json.dumps(characters[user_id]['stats'])}\n"
                f"Passives: {json.dumps(characters[user_id]['passives'])}\n"
                f"Personality: {self.personality.value}"
            )

class CreateCharButton(View):
    def __init__(self):
        super().__init__()

    @nextcord.ui.button(label="Create Character", style=ButtonStyle.primary)
    async def create_callback(self, button: Button, interaction: Interaction):
        await interaction.response.send_modal(CreateCharModal())

@bot.command()
async def charui(ctx):
    await ctx.send("Click below to create your character:", view=CreateCharButton())

@bot.command()
async def inventory(ctx):
    user_id = str(ctx.author.id)
    char = characters.get(user_id)
    if not char:
        await ctx.send("You haven't created a character yet.")
        return

    inv_items = char.get("inventory", [])
    if not inv_items:
        await ctx.send("Your inventory is empty.")
        return

    class InventoryView(View):
        def __init__(self, items):
            super().__init__()
            for item in items:
                self.add_item(Button(label=item, style=ButtonStyle.secondary))

    await ctx.send("Your Inventory:", view=InventoryView(inv_items))

@bot.command()
async def askdm(ctx, *, prompt: str):
    user_id = str(ctx.author.id)
    d20_bonus = 0
    char = characters.get(user_id)

    if char:
        if "Ambidextrous" in char.get("passives", []) and "hands" in prompt:
            d20_bonus += 2
        personality = char.get("personality", "")
        char_desc = f"You are {char['name']}, a {char['race']} {char['class']} with a {personality} personality."
    else:
        char_desc = "You are an unnamed adventurer."

    roll_result = roll_formula("2d6+{0}".format(d20_bonus))
    await ctx.send(f"You rolled a **{roll_result}** on your action.")

    system_prompt = (
        "Assume the role of an expert fantasy writer that specializes in interactive fiction..."
    )

    log_channel = nextcord.utils.get(ctx.guild.text_channels, name="logs")
    quest_id = 1
    memory_messages = []

    if log_channel:
        async for msg in log_channel.history(limit=50, oldest_first=True):
            if msg.author == bot.user and "**DM Reply:**" in msg.content:
                try:
                    quest_line = int(msg.content.split("Quest ID: #")[1].split("\n")[0])
                    if quest_line >= quest_id:
                        quest_id = quest_line + 1
                    user_input = msg.content.split("Prompt:** ")[1].split("\n**DM Reply:**")[0]
                    bot_reply = msg.content.split("**DM Reply:** ")[1]
                    memory_messages.append({"role": "user", "content": user_input})
                    memory_messages.append({"role": "assistant", "content": bot_reply})
                except:
                    continue

    messages = [{"role": "system", "content": system_prompt}] + memory_messages
    messages.append({"role": "user", "content": f"{char_desc} {prompt} (Roll: {roll_result})"})

    payload = {
        "model": "mistralai/mistral-7b-instruct",
        "messages": messages
    }

    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }

    try:
        res = requests.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload)
        data = res.json()
        reply = data['choices'][0]['message']['content'].strip()
        await ctx.send(f"**DM Reply:** {reply}")

        timestamp = datetime.now().strftime("%B %d, %Y – %I:%M %p")
        if log_channel:
            await log_channel.send(
                f"Quest ID: #{quest_id}\n"
                f"Timestamp: {timestamp}\n"
                f"Prompt:** {prompt} (Roll: {roll_result})\n"
                f"**DM Reply:** {reply}"
            )

    except Exception as e:
        await ctx.send(f"❌ Bot error: {str(e)}")

bot.run(DISCORD_TOKEN)
