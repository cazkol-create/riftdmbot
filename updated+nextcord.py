# main.py
import os
import json
import random
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

@bot.event
async def on_ready():
    print(f"✅ Rift DM is online as {bot.user}!")

def roll_d20(stat_bonus=0):
    return min(20, max(1, random.randint(1, 20) + stat_bonus))

# Character creation via command (fallback)
@bot.command()
async def createchar(ctx, name: str, race: str, char_class: str):
    user_id = str(ctx.author.id)
    characters[user_id] = {
        "name": name,
        "race": race,
        "class": char_class,
        "passives": [],
        "stats": {
            "strength": 10,
            "dexterity": 10,
            "intelligence": 10
        }
    }
    await ctx.send(f"Character created for {ctx.author.display_name}:\n"
                   f"Name: `{name}`\nRace: `{race}`\nClass: `{char_class}`")

# View character
@bot.command()
async def mychar(ctx):
    user_id = str(ctx.author.id)
    char = characters.get(user_id)
    if char:
        stats = char['stats']
        await ctx.send(f"{ctx.author.display_name}'s Character:\n"
                       f"Name: `{char['name']}`\nRace: `{char['race']}`\nClass: `{char['class']}`\n"
                       f"Stats: {json.dumps(stats)}\nPassives: {', '.join(char['passives']) if char['passives'] else 'None'}")
    else:
        await ctx.send("You haven’t created a character yet. Use `!charui` or `!createchar`.")

# Delete character
@bot.command()
async def deletechar(ctx):
    user_id = str(ctx.author.id)
    if user_id in characters:
        del characters[user_id]
        await ctx.send("🗑️ Your character has been deleted.")
    else:
        await ctx.send("You don’t have a character to delete.")

# Party setup
@bot.command()
async def startparty(ctx, *members):
    global party_members, current_turn
    party_members = list(members)
    current_turn = 0
    if party_members:
        await ctx.send(f"Party order set: {', '.join(party_members)}\n➡️ It's **{party_members[0]}'s** turn!")
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

# Ask the DM
@bot.command()
async def askdm(ctx, *, prompt: str):
    user_id = str(ctx.author.id)
    d20_bonus = 0

    # Passive bonus logic
    if user_id in characters:
        char = characters[user_id]
        if "Expertise in Sleight of Hand" in char.get("passives", []):
            if "pick" in prompt.lower() or "steal" in prompt.lower():
                d20_bonus += 2

    d20 = roll_d20(d20_bonus)
    await ctx.send(f"You rolled a **{d20}** on your action.")

    system_prompt = (
        "Assume the role of an expert fantasy writer that specializes in interactive fiction..."
        "Use the d20 roll I provide to determine the success or failure of actions or events..."
        "Never describe what the player or their companions are doing. Keep all responses to 80 words or less."
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

    if user_id in characters:
        char = characters[user_id]
        char_desc = f"You are {char['name']}, a {char['race']} {char['class']}."
    else:
        char_desc = "You are an unnamed adventurer."

    messages = [{"role": "system", "content": system_prompt}] + memory_messages
    messages.append({"role": "user", "content": f"{char_desc} {prompt} (Roll: {d20})"})

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
                f"Prompt:** {prompt} (d20: {d20})\n"
                f"**DM Reply:** {reply}"
            )

    except Exception as e:
        await ctx.send(f"❌ Bot error: {str(e)}")

# UI: Character Creation Modal
class CreateCharModal(Modal):
    def __init__(self):
        super().__init__("Create Your Character")
        self.name = TextInput(label="Name", placeholder="Your character's name", style=TextInputStyle.short)
        self.race = TextInput(label="Race", placeholder="Elf, Human, Orc...", style=TextInputStyle.short)
        self.char_class = TextInput(label="Class", placeholder="Warrior, Mage, etc.", style=TextInputStyle.short)

        self.add_item(self.name)
        self.add_item(self.race)
        self.add_item(self.char_class)

    async def callback(self, interaction: Interaction):
        user_id = str(interaction.user.id)
        characters[user_id] = {
            "name": self.name.value,
            "race": self.race.value,
            "class": self.char_class.value,
            "passives": [],
            "stats": {
                "strength": 10,
                "dexterity": 10,
                "intelligence": 10
            }
        }
        await interaction.response.send_message(f"✅ Character `{self.name.value}` created!", ephemeral=True)

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
async def helpme(ctx):
    await ctx.send(
        "**Rift DM Bot Commands:**\n"
        "`!charui` - Create character with UI\n"
        "`!createchar <name> <race> <class>` - Create character (manual)\n"
        "`!mychar` - View your character\n"
        "`!deletechar` - Delete your character\n"
        "`!startparty <name1> <name2>...` - Start a turn-based party\n"
        "`!nextturn` - Progress to next turn\n"
        "`!addmember <name>` - Add a new member to party\n"
        "`!endparty` - End party session\n"
        "`!askdm <prompt>` - Ask the Dungeon Master\n"
        "`!helpme` - Show this help message"
    )

bot.run(DISCORD_TOKEN)
