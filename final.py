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
async def deletechar(ctx):
    user_id = str(ctx.author.id)
    if user_id in characters:
        del characters[user_id]
        await ctx.send(f"🗑️ Your character has been deleted, {ctx.author.display_name}.")
    else:
        await ctx.send("❌ You don’t have a character to delete.")

@bot.command()
async def charui(ctx):
    await ctx.send("Click below to create your character:", view=CreateCharButton())

@bot.command()
async def createchar(ctx, name: str, race: str, char_class: str):
    user_id = str(ctx.author.id)
    characters[user_id] = {
        "name": name,
        "race": race,
        "class": char_class,
        "stats": {
            "strength": 10,
            "dexterity": 10,
            "intelligence": 10
        },
        "passives": [],
        "personality": "",
        "inventory": []
    }
    await ctx.send(f"Character created for {ctx.author.display_name}:
"
                   f"Name: `{name}`
Race: `{race}`
Class: `{char_class}`")

@bot.command()
async def mychar(ctx):
    user_id = str(ctx.author.id)
    char = characters.get(user_id)
    if char:
        stats = char['stats']
        await ctx.send(f"{ctx.author.display_name}'s Character:
"
                       f"Name: `{char['name']}`
Race: `{char['race']}`
Class: `{char['class']}`
"
                       f"Stats: {json.dumps(stats)}
"
                       f"Passives: {', '.join(char['passives']) if char['passives'] else 'None'}")
    else:
        await ctx.send("You haven’t created a character yet. Use `!createchar`.")

@bot.command()
async def startparty(ctx, *members):
    global party_members, current_turn
    party_members = list(members)
    current_turn = 0
    if party_members:
        await ctx.send(f"Party order set: {', '.join(party_members)}
➡️ It's **{party_members[0]}'s** turn!")
    else:
        await ctx.send("You must specify at least one party member.")

@bot.command()
async def nextturn(ctx):
    global current_turn
    if not party_members:
        await ctx.send("No party members set. Use `!startparty` first.")
        return
    current_turn = (current_turn + 1) % len(party_members)
    await ctx.send(f"➡️ It's now **{party_members[current_turn]}'s** turn!")

@bot.command()
async def addmember(ctx, member: str):
    global party_members
    party_members.append(member)
    await ctx.send(f"Added {member} to the party. Current order: {', '.join(party_members)}")

@bot.command()
async def endparty(ctx):
    global party_members, current_turn
    party_members = []
    current_turn = 0
    await ctx.send("Party turn tracking ended.")

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
                    quest_line = int(msg.content.split("Quest ID: #")[1].split("
")[0])
                    if quest_line >= quest_id:
                        quest_id = quest_line + 1
                    user_input = msg.content.split("Prompt:** ")[1].split("
**DM Reply:**")[0]
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
                f"Quest ID: #{quest_id}
"
                f"Timestamp: {timestamp}
"
                f"Prompt:** {prompt} (Roll: {roll_result})
"
                f"**DM Reply:** {reply}"
            )

    except Exception as e:
        await ctx.send(f"❌ Bot error: {str(e)}")

@bot.command()
async def helpme(ctx):
    await ctx.send(
        "**Rift DM Bot Commands:**\n"
        "`!createchar <name> <race> <class>` - Create your character\n"
        "`!deletechar` - Delete your character\n"
        "`!mychar` - View your character\n"
        "`!startparty <name1> <name2>...` - Start a turn-based party\n"
        "`!nextturn` - Progress to next turn\n"
        "`!addmember <name>` - Add a new member to party\n"
        "`!endparty` - End party session\n"
        "`!askdm <prompt>` - Ask the Dungeon Master\n"
        "`!charui` - Create a character using buttons\n"
        "`!helpme` - Show this help message\n"
        "Use the buttons that appear during party sessions for UI control."
    )
