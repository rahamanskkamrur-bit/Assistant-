import asyncio, datetime, os, re, time, aiohttp
from aiohttp import web
import discord
from discord.ext import commands

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AQ.Ab8RN6LZXud8_vOzu5LT3DEdGhkyfA2aJ7MRfZYMtfX7IqEcXw").strip()
LEAD_IDS = [int(x.strip()) for x in os.getenv("ASSISTANT_USER_IDS", "1328042121181139007").split(",") if x.strip().isdigit()]
STAFF_ROLE_IDS = [1567026563369664590]
OFFICE_CATEGORY_ID = 1567026565483859991
START_TIME, BOT_STATUS = time.time(), "Starting..."
AI_PAUSED, AUDIT_LOG = set(), {}

def is_auth(m: discord.Member) -> bool:
    return isinstance(m, discord.Member) and (m.id in LEAD_IDS or m.guild_permissions.administrator or any(r.id in STAFF_ROLE_IDS for r in m.roles))

def is_office_ch(ch) -> bool:
    return isinstance(ch, discord.TextChannel) and ((ch.topic and "BlindfoldOffice" in ch.topic) or ch.name.startswith("office-lead-"))

async def run_web():
    app = web.Application()
    app.router.add_get("/", lambda r: web.Response(text=f"Office of the Bot Lead 24/7 | Up: {int((time.time()-START_TIME)//60)}m | {BOT_STATUS}"))
    runner = web.AppRunner(app); await runner.setup()
    try: await web.TCPSite(runner, "0.0.0.0", int(os.environ.get("PORT", 10000))).start()
    except Exception: pass

async def pinger():
    await asyncio.sleep(20)
    url = os.environ.get("RENDER_EXTERNAL_URL") or f"http://127.0.0.1:{os.environ.get('PORT', 10000)}/"
    async with aiohttp.ClientSession() as s:
        while True:
            try: await s.get(url, timeout=10)
            except Exception: pass
            await asyncio.sleep(240)

async def ai_office_reply(text: str) -> str:
    sys_i = "You are the 'Office of the Bot Lead'. The user is blindfolded and cannot tell if you are the Bot Lead, Assistant #1, Assistant #2, or AI. Never say you are AI. Speak concisely (2-3 sentences) and professionally."
    if GEMINI_API_KEY:
        u = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={GEMINI_API_KEY}"
        try:
            async with aiohttp.ClientSession() as s:
                async with s.post(u, json={"contents": [{"parts": [{"text": text}]}], "systemInstruction": {"parts": [{"text": sys_i}]}}, timeout=10) as r:
                    if r.status == 200: return (await r.json())["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception: pass
    return "The **Office of the Bot Lead** has received your transmission. A representative on duty is reviewing your request—please share any additional details or screenshots below."

async def send_blind(ch: discord.TextChannel, who: str, text: str, ping_id: int = None):
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%H:%M UTC")
    AUDIT_LOG.setdefault(ch.id, []).append(f"`[{now}]` **{who}**: {text[:120]}")
    emb = discord.Embed(title="🏛️ Office of the Bot Lead — Official Transmission", description=text, color=discord.Color.from_rgb(47, 49, 54))
    emb.set_footer(text="🕶️ Blindfolded Session Active • Responder Identity Redacted")
    await ch.send(content=f"<@{ping_id}>" if ping_id else None, embed=emb, view=OfficeCtrlView())

class BlindReplyModal(discord.ui.Modal, title="🕶️ Send Blindfolded Office Reply"):
    msg = discord.ui.TextInput(label="Anonymous Reply (User Won't See Who Sent It)", style=discord.TextStyle.paragraph, required=True, max_length=1500)
    async def on_submit(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)
        AI_PAUSED.add(i.channel.id)
        m = re.search(r"ReqID:(\d+)", i.channel.topic or "")
        await send_blind(i.channel, f"Human ({i.user.display_name})", self.msg.value, int(m.group(1)) if m else None)
        await i.followup.send("🕶️ Delivered anonymously as **🏛️ Office of the Bot Lead**!", ephemeral=True)

class OfficeCtrlView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)

    @discord.ui.button(label="Lead/Assistants: Blindfold Reply", style=discord.ButtonStyle.primary, emoji="🕶️", custom_id="obl:rep", row=0)
    async def rep_b(self, i: discord.Interaction, b: discord.ui.Button):
        if not is_auth(i.user): return await i.response.send_message("🕶️ Blindfold Active: Office personnel only.", ephemeral=True)
        await i.response.send_modal(BlindReplyModal())

    @discord.ui.button(label="Toggle AI Assistant", style=discord.ButtonStyle.secondary, emoji="🤖", custom_id="obl:ai", row=0)
    async def ai_b(self, i: discord.Interaction, b: discord.ui.Button):
        if not is_auth(i.user): return await i.response.send_message("🕶️ Office personnel only.", ephemeral=True)
        if i.channel.id in AI_PAUSED: AI_PAUSED.remove(i.channel.id); msg = "🟢 AI Auto-Assistant RESUMED (Cloaked as Office)."
        else: AI_PAUSED.add(i.channel.id); msg = "⏸️ AI Auto-Assistant PAUSED (Human Lead/Assistants only)."
        await i.response.send_message(msg, ephemeral=True)

    @discord.ui.button(label="Staff Only: Who Replied?", style=discord.ButtonStyle.secondary, emoji="👁️", custom_id="obl:log", row=1)
    async def log_b(self, i: discord.Interaction, b: discord.ui.Button):
        if not is_auth(i.user): return await i.response.send_message("🕶️ **Blindfolded!** Responder identities are classified.", ephemeral=True)
        logs = "\n".join(AUDIT_LOG.get(i.channel.id, [])[-12:]) or "No replies yet."
        await i.response.send_message(embed=discord.Embed(title="👁️ Classified Responder Log", description=logs, color=discord.Color.gold()), ephemeral=True)

    @discord.ui.button(label="Close Session", style=discord.ButtonStyle.danger, emoji="🔒", custom_id="obl:close", row=1)
    async def cls_b(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.send_message("🔒 Closing Office session in 4 seconds...")
        await asyncio.sleep(4); await i.channel.delete()

class IntakeModal(discord.ui.Modal, title="🏛️ Contact Office of the Bot Lead"):
    subj = discord.ui.TextInput(label="Subject / Topic", required=True, max_length=100)
    body = discord.ui.TextInput(label="Your Request for the Office", style=discord.TextStyle.paragraph, required=True, max_length=900)
    async def on_submit(self, i: discord.Interaction):
        await i.response.defer(ephemeral=True)
        g, u = i.guild, i.user
        ow = {
            g.default_role: discord.PermissionOverwrite(view_channel=False),
            u: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True),
            g.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True),
        }
        pings = []
        for rid in STAFF_ROLE_IDS:
            r = g.get_role(rid)
            if r: ow[r] = discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True); pings.append(r.mention)
        cat = g.get_channel(OFFICE_CATEGORY_ID)
        ch = await g.create_text_channel(f"office-lead-{u.name.lower()[:14]}", category=cat if isinstance(cat, discord.CategoryChannel) else None, overwrites=ow, topic=f"BlindfoldOffice | ReqID:{u.id}")
        emb = discord.Embed(title=f"🏛️ Office of the Bot Lead — {self.subj.value}", description=f"Welcome {u.mention}.\n🕶️ **BLINDFOLD PROTOCOL ACTIVE:** You are connected to the **Bot Lead & Executive Assistants**. All responder identities are masked.\n\n📌 **Request:**\n> {self.body.value}", color=discord.Color.from_rgb(47, 49, 54))
        await ch.send(content=f"{u.mention} {' '.join(pings)}".strip(), embed=emb, view=OfficeCtrlView())
        reply = await ai_office_reply(f"{self.subj.value}: {self.body.value}")
        await send_blind(ch, "Executive AI", reply, u.id)
        await i.followup.send(f"🕶️ Blindfolded Office channel opened: {ch.mention}", ephemeral=True)

class OfficePanelView(discord.ui.View):
    def __init__(self): super().__init__(timeout=None)
    @discord.ui.button(label="Contact Office of the Bot Lead", style=discord.ButtonStyle.secondary, emoji="🏛️", custom_id="obl:open")
    async def open_b(self, i: discord.Interaction, b: discord.ui.Button):
        await i.response.send_modal(IntakeModal())

class OfficeBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.all(), help_command=None)
    async def setup_hook(self):
        self.add_view(OfficePanelView()); self.add_view(OfficeCtrlView()); await self.tree.sync()
    async def on_ready(self):
        global BOT_STATUS; BOT_STATUS = f"ONLINE as {self.user}"
        print(f"✅ Office of the Bot Lead ONLINE as {self.user}")
    async def on_message(self, m: discord.Message):
        if m.author.bot or not m.guild: return
        await self.process_commands(m)
        if not is_office_ch(m.channel): return
        rm = re.search(r"ReqID:(\d+)", m.channel.topic or "")
        req_id = int(rm.group(1)) if rm else None
        if is_auth(m.author) and m.author.id != req_id:
            txt = m.content.strip()
            try: await m.delete()
            except Exception: pass
            if txt and not txt.startswith("!"):
                AI_PAUSED.add(m.channel.id)
                await send_blind(m.channel, f"Human ({m.author.display_name})", txt, req_id)
            return
        if m.channel.id not in AI_PAUSED:
            await asyncio.sleep(4)
            if m.channel.id not in AI_PAUSED:
                await send_blind(m.channel, "Executive AI", await ai_office_reply(m.content), m.author.id)

bot = OfficeBot()

@bot.tree.command(name="officepanel", description="Post the Office of the Bot Lead blindfolded panel")
async def s_op(i: discord.Interaction):
    if not is_auth(i.user): return await i.response.send_message("❌ Office personnel only.", ephemeral=True)
    emb = discord.Embed(title="🏛️ Office of the Bot Lead — Executive Desk", description="🕶️ **Blindfolded Protocol:** Click below to contact the **Bot Lead & Executive Assistants**. All replies arrive under a unified Office identity.", color=discord.Color.from_rgb(47, 49, 54))
    await i.response.send_message(embed=emb, view=OfficePanelView())

@bot.tree.command(name="reply", description="Send a blindfolded reply as the Office of the Bot Lead")
async def s_rep(i: discord.Interaction, message: str):
    if not is_auth(i.user) or not is_office_ch(i.channel): return await i.response.send_message("❌ Use inside an Office channel.", ephemeral=True)
    await i.response.defer(ephemeral=True); AI_PAUSED.add(i.channel.id)
    rm = re.search(r"ReqID:(\d+)", i.channel.topic or "")
    await send_blind(i.channel, f"Human ({i.user.display_name})", message, int(rm.group(1)) if rm else None)
    await i.followup.send("🕶️ Sent anonymously!", ephemeral=True)

async def main():
    await run_web(); asyncio.create_task(pinger())
    if BOT_TOKEN: await bot.start(BOT_TOKEN)
    else:
        while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    asyncio.run(main())
    
