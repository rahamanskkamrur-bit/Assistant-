import asyncio
import datetime
import os
import re
import time
import aiohttp
from aiohttp import web
import discord
from discord.ext import commands

# ==============================================================================
# 🏛️ OFFICE OF THE BOT LEAD — BLINDFOLDED EXECUTIVE ASSISTANT BOT (24/7)
# ==============================================================================
# HOW THE "BLINDFOLD" SYSTEM WORKS FOR YOU & YOUR 2 ASSISTANTS:
#   1. When a user opens a request, they are BLINDFOLDED inside a private room.
#   2. Whether YOU (Bot Lead), ASSISTANT #1, ASSISTANT #2, or the BUILT-IN AI
#      replies, the user ONLY ever sees:
#         "🏛️ Office of the Bot Lead — Official Transmission"
#   3. ZERO TYPING INDICATOR LEAK:
#      • Click "🕶️ Send Blindfolded Reply" (opens a popup Modal so Discord NEVER
#        shows "User is typing..." to the requester!), OR
#      • Use `/reply <message>`, OR
#      • Even if you or your 2 assistants type directly in the channel, the bot
#        deletes your message in <0.1 seconds and re-posts it as the Office!
#   4. INTERNAL STAFF AUDIT LOG:
#      • Only you and your 2 assistants can click "👁️ Staff Only: Who Replied?"
#        to see which assistant sent each blindfolded message!
# ==============================================================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv(
    "GEMINI_API_KEY",
    "AQ.Ab8RN6LZXud8_vOzu5LT3DEdGhkyfA2aJ7MRfZYMtfX7IqEcXw",
).strip()

# Put your Discord User ID and your 2 Assistants' User IDs here (or use STAFF_ROLE_IDS)
BOT_LEAD_AND_ASSISTANT_IDS = [
    int(x.strip()) for x in os.getenv("ASSISTANT_USER_IDS", "").split(",") if x.strip().isdigit()
]
STAFF_ROLE_IDS = [1567026563369664590]
OFFICE_CATEGORY_ID = 1567026565483859991
OFFICE_LOG_CHANNEL_ID = 1567026568423931975

START_TIME = time.time()
BOT_STATUS = "Starting..."

# Tracks channels where AI Auto-Assistant is paused because a human (Lead or Assistant 1/2) took over
AI_PAUSED_CHANNELS = set()
# Internal secret log so ONLY Staff know whether Bot Lead, Assistant 1, Assistant 2, or AI sent a reply
# {channel_id: [{"time": str, "sender": str, "text": str}]}
BLINDFOLD_AUDIT_LOG = {}


def is_office_authorized(member: discord.Member) -> bool:
    """Returns True ONLY for the Bot Lead, the 2 Assistants, or Staff Role holders."""
    if not isinstance(member, discord.Member):
        return False
    if member.id in BOT_LEAD_AND_ASSISTANT_IDS:
        return True
    return (
        member.guild_permissions.administrator
        or member.guild_permissions.manage_guild
        or any(r.id in STAFF_ROLE_IDS for r in member.roles)
    )


def is_office_channel(channel: discord.TextChannel) -> bool:
    if not isinstance(channel, discord.TextChannel):
        return False
    return bool(channel.topic and "BlindfoldOffice" in channel.topic) or channel.name.startswith("office-lead-")


# ==============================================================================
# 1. 24/7 KEEP-ALIVE WEB SERVER & AUTO-PINGER (NO SUBSCRIPTION NEEDED)
# ==============================================================================
async def handle_ping(req):
    up = int((time.time() - START_TIME) // 60)
    return web.Response(text=f"Office of the Bot Lead 24/7 | Uptime: {up}m | Status: {BOT_STATUS}")


async def run_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    try:
        await web.TCPSite(runner, "0.0.0.0", port).start()
    except Exception:
        pass


async def self_ping_loop():
    await asyncio.sleep(20)
    url = os.environ.get("RENDER_EXTERNAL_URL") or f"http://127.0.0.1:{os.environ.get('PORT', 10000)}/"
    headers = {"User-Agent": "Mozilla/5.0 OfficeBotLead/24-7", "Cache-Control": "no-cache"}
    async with aiohttp.ClientSession(headers=headers) as s:
        while True:
            try:
                async with s.get(url, timeout=10):
                    pass
            except Exception:
                pass
            await asyncio.sleep(240)


# ==============================================================================
# 2. BLINDFOLDED MESSAGE SENDER & AI EXECUTIVE ASSISTANT ENGINE
# ==============================================================================
def build_blindfold_embed(message_text: str) -> discord.Embed:
    """
    Builds the uniform anonymous embed so the requester has ZERO clue whether
    the Bot Lead, Assistant #1, Assistant #2, or the AI Assistant is speaking.
    """
    emb = discord.Embed(
        title="🏛️ Office of the Bot Lead — Official Transmission",
        description=message_text,
        color=discord.Color.from_rgb(47, 49, 54),
    )
    emb.set_footer(text="🕶️ Blindfolded Session Active • Responder Identity Redacted")
    return emb


async def send_blindfolded_response(
    channel: discord.TextChannel,
    actual_sender_label: str,
    message_text: str,
    ping_user_id: int = None,
):
    """Logs who really sent the message privately for staff, then posts the cloaked response."""
    now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M UTC")
    history = BLINDFOLD_AUDIT_LOG.setdefault(channel.id, [])
    history.append({"time": now_str, "sender": actual_sender_label, "text": message_text[:180]})

    ping_str = f"<@{ping_user_id}>" if ping_user_id else None
    await channel.send(
        content=ping_str,
        embed=build_blindfold_embed(message_text),
        view=OfficeSessionControlView(),
    )


async def generate_executive_ai_reply(user_text: str) -> str:
    """Acts as the Office of the Bot Lead when the Bot Lead & 2 Assistants are busy."""
    sys_inst = (
        "You are speaking as the 'Office of the Bot Lead'. "
        "The user talking to you is 'blindfolded'—they do not know if they are speaking to the Bot Lead, "
        "Assistant #1, Assistant #2, or the automated Executive Assistant. "
        "Never reveal that you are an AI. Speak professionally, authoritatively, and concisely (2-3 sentences) "
        "as a representative of the Office of the Bot Lead. Ask clarifying questions about their bot request, "
        "issue, or inquiry so the Office can resolve it."
    )

    # 1. Try Gemini API
    if GEMINI_API_KEY:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
        payload = {
            "contents": [{"parts": [{"text": f"Requester says: {user_text}\nOffice of the Bot Lead response:"}]}],
            "systemInstruction": {"parts": [{"text": sys_inst}]},
        }
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(url, json=payload, timeout=10) as r:
                    if r.status == 200:
                        d = await r.json()
                        reply = d["candidates"][0]["content"]["parts"][0]["text"].strip()
                        if reply:
                            return reply
        except Exception:
            pass

    # 2. Try Keyless LLM7 OpenAI Gateway
    try:
        headers = {"Content-Type": "application/json", "Authorization": "Bearer unused"}
        payload = {
            "model": "gpt-4o-mini",
            "messages": [
                {"role": "system", "content": sys_inst},
                {"role": "user", "content": user_text},
            ],
        }
        async with aiohttp.ClientSession(headers=headers) as s:
            async with s.post("https://api.llm7.io/v1/chat/completions", json=payload, timeout=10) as r:
                if r.status == 200:
                    d = await r.json()
                    reply = d["choices"][0]["message"]["content"].strip()
                    if reply:
                        return reply
    except Exception:
        pass

    # 3. Built-in Professional Fallback
    low = user_text.lower()
    if any(w in low for w in ["bot", "script", "code", "command", "bug", "error", "offline"]):
        return (
            "Your technical report has been received by the **Office of the Bot Lead**. "
            "Please specify which bot or command is affected and include any screenshots so a representative on duty can action this immediately."
        )
    return (
        "The **Office of the Bot Lead** has received your transmission. "
        "A representative on duty is reviewing your message now—please provide any additional details or context below."
    )


# ==============================================================================
# 3. BLINDFOLDED REPLY MODAL & SESSION CONTROL BUTTONS
# ==============================================================================
class BlindfoldReplyModal(discord.ui.Modal, title="🕶️ Send Blindfolded Office Reply"):
    def __init__(self):
        super().__init__()
        self.reply_box = discord.ui.TextInput(
            label="Your Message (Sent Anonymously as The Office)",
            style=discord.TextStyle.paragraph,
            placeholder="Type your response here. The user will NOT see your name, avatar, or typing indicator...",
            required=True,
            max_length=1500,
        )
        self.add_item(self.reply_box)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        # Pause AI automatically since the Bot Lead or one of the 2 Assistants is replying
        AI_PAUSED_CHANNELS.add(interaction.channel.id)

        topic = interaction.channel.topic or ""
        m = re.search(r"RequesterID:(\d+)", topic)
        req_id = int(m.group(1)) if m else None

        await send_blindfolded_response(
            interaction.channel,
            f"Human ({interaction.user.display_name})",
            self.reply_box.value,
            ping_user_id=req_id,
        )
        await interaction.followup.send(
            "🕶️ **Blindfolded reply delivered!** The requester only sees **🏛️ Office of the Bot Lead**.",
            ephemeral=True,
        )


class OfficeSessionControlView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Lead/Assistants: Send Blindfolded Reply", style=discord.ButtonStyle.primary, emoji="🕶️", custom_id="obl:reply", row=0)
    async def blind_reply_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_office_authorized(interaction.user):
            return await interaction.response.send_message(
                "🕶️ **Blindfold Active:** Only the **Office of the Bot Lead** and authorized Assistants can use this control.",
                ephemeral=True,
            )
        await interaction.response.send_modal(BlindfoldReplyModal())

    @discord.ui.button(label="Toggle Auto-Assistant", style=discord.ButtonStyle.secondary, emoji="🤖", custom_id="obl:toggle_ai", row=0)
    async def toggle_ai_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_office_authorized(interaction.user):
            return await interaction.response.send_message("🕶️ Authorized Office personnel only.", ephemeral=True)
        cid = interaction.channel.id
        if cid in AI_PAUSED_CHANNELS:
            AI_PAUSED_CHANNELS.remove(cid)
            await interaction.response.send_message(
                "🟢 **AI Executive Assistant RESUMED** for this channel (still completely disguised as the Office!).",
                ephemeral=True,
            )
        else:
            AI_PAUSED_CHANNELS.add(cid)
            await interaction.response.send_message(
                "⏸️ **AI Executive Assistant PAUSED** — Only you and your 2 Assistants will reply here.",
                ephemeral=True,
            )

    @discord.ui.button(label="Staff Only: Who Replied?", style=discord.ButtonStyle.secondary, emoji="👁️", custom_id="obl:audit", row=1)
    async def audit_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not is_office_authorized(interaction.user):
            return await interaction.response.send_message(
                "🕶️ **Nice try!** You are blindfolded—responder identities are strictly classified by the **Office of the Bot Lead**.",
                ephemeral=True,
            )
        logs = BLINDFOLD_AUDIT_LOG.get(interaction.channel.id, [])
        if not logs:
            return await interaction.response.send_message("📋 No blindfolded replies sent in this session yet.", ephemeral=True)
        lines = [f"`[{x['time']}]` **{x['sender']}**: {x['text']}" for x in logs[-12:]]
        emb = discord.Embed(
            title="👁️ Classified Internal Responder Log (Hidden from Requester)",
            description="\n".join(lines),
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=emb, ephemeral=True)

    @discord.ui.button(label="Close Office Session", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="obl:close", row=1)
    async def close_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("🔒 **Office of the Bot Lead** session concluded. Closing channel in 5 seconds...")
        await asyncio.sleep(5)
        await interaction.channel.delete()


# ==============================================================================
# 4. REQUEST INTAKE MODAL & PUBLIC OFFICE PANEL (/officepanel)
# ==============================================================================
class RequestLeadModal(discord.ui.Modal, title="🏛️ Contact Office of the Bot Lead"):
    def __init__(self):
        super().__init__()
        self.subject = discord.ui.TextInput(
            label="Subject / Topic of Request",
            placeholder="e.g. Bot Feature Request, Bug Report, Direct Inquiry",
            required=True,
            max_length=100,
        )
        self.details = discord.ui.TextInput(
            label="Full Message for the Office of the Bot Lead",
            style=discord.TextStyle.paragraph,
            placeholder="Explain your request clearly...",
            required=True,
            max_length=900,
        )
        self.add_item(self.subject)
        self.add_item(self.details)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guild, user = interaction.guild, interaction.user

        for ch in guild.text_channels:
            if ch.topic and f"BlindfoldOffice | RequesterID:{user.id}" in ch.topic:
                return await interaction.followup.send(f"⚠️ You already have an active session with the Office: {ch.mention}", ephemeral=True)

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            user: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, attach_files=True),
            guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True, embed_links=True),
        }
        pings = []
        for rid in STAFF_ROLE_IDS:
            r = guild.get_role(rid)
            if r:
                overwrites[r] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)
                pings.append(r.mention)
        for uid in BOT_LEAD_AND_ASSISTANT_IDS:
            m = guild.get_member(uid)
            if m:
                overwrites[m] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True)

        cat = guild.get_channel(OFFICE_CATEGORY_ID)
        if not isinstance(cat, discord.CategoryChannel):
            cat = None

        ch = await guild.create_text_channel(
            name=f"office-lead-{user.name.lower()[:15]}",
            category=cat,
            overwrites=overwrites,
            topic=f"BlindfoldOffice | RequesterID:{user.id}",
        )

        intro_emb = discord.Embed(
            title=f"🏛️ Office of the Bot Lead — {self.subject.value}",
            description=(
                f"Welcome {user.mention}.\n\n"
                "🕶️ **BLINDFOLD PROTOCOL ACTIVE:**\n"
                "You are now connected to the **Office of the Bot Lead** (The Bot Lead & Executive Assistants). "
                "For security and neutrality, **all responder identities are blindfolded**—you will not see which member of the Office is responding to you.\n\n"
                f"📌 **Your Initial Request:**\n> {self.details.value}"
            ),
            color=discord.Color.from_rgb(47, 49, 54),
        )
        intro_emb.set_footer(text="Office of the Bot Lead • Blindfolded Executive Channel")
        await ch.send(content=f"{user.mention} {' '.join(pings)}".strip(), embed=intro_emb, view=OfficeSessionControlView())

        # Send immediate first response from the AI Executive Assistant (disguised as the Office)
        initial_reply = await generate_executive_ai_reply(f"{self.subject.value}: {self.details.value}")
        await send_blindfolded_response(ch, "Executive AI Assistant", initial_reply, ping_user_id=user.id)

        await interaction.followup.send(f"🕶️ Connected to the **Office of the Bot Lead** in {ch.mention}!", ephemeral=True)


class OfficePanelView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Contact Office of the Bot Lead", style=discord.ButtonStyle.secondary, emoji="🏛️", custom_id="obl_panel:open")
    async def open_office_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RequestLeadModal())


# ==============================================================================
# 5. BOT CLASS & AUTOMATIC BLINDFOLD CLOAKING ON EVERY MESSAGE
# ==============================================================================
class OfficeOfBotLead(commands.Bot):
    def __init__(self, msg_intent: bool = True):
        intents = discord.Intents.default()
        intents.message_content = msg_intent
        super().__init__(command_prefix="!", intents=intents, help_command=None)

    async def setup_hook(self):
        self.add_view(OfficePanelView())
        self.add_view(OfficeSessionControlView())
        await self.tree.sync()

    async def on_ready(self):
        global BOT_STATUS
        BOT_STATUS = f"ONLINE as {self.user}"
        await self.change_presence(
            status=discord.Status.online,
            activity=discord.Activity(type=discord.ActivityType.watching, name="🏛️ Office of the Bot Lead"),
        )
        print(f"✅ Office of the Bot Lead ONLINE as {self.user}")

    async def on_message(self, message: discord.Message):
        if message.author.bot or not message.guild:
            return
        await self.process_commands(message)

        if not is_office_channel(message.channel):
            return

        topic = message.channel.topic or ""
        m = re.search(r"RequesterID:(\d+)", topic)
        requester_id = int(m.group(1)) if m else None

        # CASE 1: The Bot Lead or one of the 2 Assistants types directly in the channel!
        # -> Instantly DELETE their message and re-post it anonymously as "Office of the Bot Lead"!
        if is_office_authorized(message.author) and message.author.id != requester_id:
            raw_text = message.content.strip()
            try:
                await message.delete()
            except Exception:
                pass
            if not raw_text or raw_text.startswith("!"):
                return
            AI_PAUSED_CHANNELS.add(message.channel.id)
            await send_blindfolded_response(
                message.channel,
                f"Human ({message.author.display_name})",
                raw_text,
                ping_user_id=requester_id,
            )
            return

        # CASE 2: T
