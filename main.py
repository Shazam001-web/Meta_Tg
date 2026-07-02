# ========================================================================
# TELEGRAM MASS REPORT SWARM — By: Dev Shazam
# python 3.10+ | pyrogram
# ========================================================================
#
# First run: logs in interactively, saves session for reuse.
# Subsequent runs: loads saved session automatically.
# Optionally load more .session files from ./sessions/ for extra firepower.
#
# Requirements:
#   pip install pyrogram tgcrypto
#
# Get API_ID and API_HASH at https://my.telegram.org/apps

import asyncio
import random
import time
import os
import glob
from typing import List, Optional
from datetime import datetime

from pyrogram import Client
from pyrogram.errors import (
    FloodWait, PeerIdInvalid, UsernameNotOccupied,
    UserIdInvalid, RPCError
)

# ========================================================================
# CONFIGURATION
# ========================================================================

TARGET_USERNAME = "target_username_here"  # @username — no @ needed
REPORT_REASON = "spam"  # Options: spam, violence, child_abuse, copyright, illegal, other

# Telegram official report usernames/chats
REPORT_CHATS = [
    "Telegram",           # Official Telegram channel
    "TelegramTips",       # Alternative contact
    "t.me/abuse",         # Abuse submission channel
    "t.me/notadmin",      # Moderation contact
    "t.me/tgc",           # Telegram community moderators
]

# How many reports to send per session per interval
REPORTS_PER_SESSION = 5

# Delay range between individual reports (seconds)
REPORT_DELAY_MIN = 3
REPORT_DELAY_MAX = 7

# Delay between report rounds for each session (seconds)
ROUND_DELAY_MIN = 20
ROUND_DELAY_MAX = 40

# Total runtime target (seconds) — aim for under 45 minutes (2700s)
TOTAL_RUNTIME = 2700

# Session directory for optional extra accounts
SESSION_DIR = "./sessions/"
SESSION_PATTERN = "*.session"

# Proxy file (optional) — one per line: protocol://user:pass@ip:port
PROXY_FILE = "./proxies.txt"

# Saved session file for primary account
SESSION_FILE = "session_string.txt"

# ========================================================================
# UTILITY FUNCTIONS
# ========================================================================

def load_proxies(filepath: str) -> List[str]:
    """Load proxies from file."""
    if not os.path.exists(filepath):
        return []
    with open(filepath, 'r') as f:
        return [line.strip() for line in f if line.strip() and not line.startswith('#')]

def get_session_files(directory: str, pattern: str) -> List[str]:
    """Get all .session files in directory."""
    return glob.glob(os.path.join(directory, pattern))

def parse_proxy(proxy_str: str) -> Optional[dict]:
    """Parse proxy string into Pyrogram proxy dict."""
    try:
        proto, rest = proxy_str.split('://', 1)
        if '@' in rest:
            auth, addr = rest.rsplit('@', 1)
            user, pw = auth.split(':', 1)
            ip, port = addr.split(':', 1)
        else:
            user, pw = None, None
            ip, port = rest.split(':', 1)
        
        return {
            "scheme": proto,
            "hostname": ip,
            "port": int(port),
            "username": user,
            "password": pw
        }
    except Exception as e:
        print(f"  [x] Failed to parse proxy: {proxy_str} — {e}")
        return None

# ========================================================================
# CLIENT CREATION (for additional .session files)
# ========================================================================

async def create_client(session_name: str, proxy: Optional[dict] = None) -> Optional[Client]:
    """Create a Pyrogram client from a .session file."""
    try:
        client = Client(
            name=session_name.replace('.session', ''),
            workdir=SESSION_DIR,
            proxy=proxy,
            in_memory=False
        )
        await client.start()
        me = await client.get_me()
        print(f"  [+] Logged in as @{me.username or me.id} (ID: {me.id})")
        return client
    except Exception as e:
        print(f"  [x] Failed to start session {session_name}: {e}")
        return None

# ========================================================================
# TARGET RESOLVER
# ========================================================================

async def resolve_target(client: Client, target: str) -> Optional[int]:
    """Resolve target username or ID to user ID."""
    try:
        if target.startswith('@'):
            target = target[1:]
        user = await client.get_users(target)
        print(f"  [i] Resolved @{target} → ID: {user.id}")
        return user.id
    except (UsernameNotOccupied, PeerIdInvalid):
        try:
            user = await client.get_users(int(target))
            return user.id
        except:
            return None
    except Exception as e:
        print(f"  [x] Resolution error: {e}")
        return None

# ========================================================================
# REPORT ENGINE
# ========================================================================

async def send_report(client: Client, target_id: int, report_chat: str) -> bool:
    """Send a report to a Telegram moderation chat about the target."""
    report_messages = [
        f"⚠️ I am reporting this account.\nUser ID: {target_id}\nUsername: @{TARGET_USERNAME}\nReason: {REPORT_REASON}\nThis account is engaging in {REPORT_REASON} behavior.",
        f"🚨 Report abuse\nAccount: @{TARGET_USERNAME}\nID: {target_id}\nIssue: {REPORT_REASON}\nPlease review and take action.",
        f"🛑 Violation report\nTarget: @{TARGET_USERNAME} ({target_id})\nType: {REPORT_REASON}\nEvidence: Multiple users flagging this account.",
        f"📋 Moderator attention\n@{TARGET_USERNAME}\nThis account needs to be reviewed for {REPORT_REASON} violations.",
        f"❗️ Official report\nTo: Telegram Team\nSubject: Account violation\nAccount: @{TARGET_USERNAME} ({target_id})\nViolation: {REPORT_REASON}\nAction requested: Ban/restrict this account.",
    ]
    
    msg = random.choice(report_messages)
    
    try:
        chat = await client.get_chat(report_chat)
        await client.send_message(chat.id, msg, disable_notification=True)
        return True
    except FloodWait as e:
        print(f"  [~] Flood wait {e.value}s — waiting...")
        await asyncio.sleep(e.value)
        return False
    except PeerIdInvalid:
        return False
    except Exception as e:
        print(f"  [x] Report send error: {e}")
        return False

async def report_cycle(client: Client, target_id: int, report_chats: List[str]) -> dict:
    """Run a complete report cycle for one session."""
    stats = {"sent": 0, "failed": 0}
    
    for chat in report_chats:
        for i in range(REPORTS_PER_SESSION):
            success = await send_report(client, target_id, chat)
            if success:
                stats["sent"] += 1
            else:
                stats["failed"] += 1
            await asyncio.sleep(random.uniform(REPORT_DELAY_MIN, REPORT_DELAY_MAX))
        await asyncio.sleep(random.uniform(1, 3))
    
    return stats

# ========================================================================
# SINGLE-ACCOUNT LOGIN + SWARM LAUNCH
# ========================================================================

async def login_or_load() -> Optional[Client]:
    """
    First-run: prompt for API credentials + phone + OTP.
    Subsequent runs: load saved string session.
    Returns an authenticated Client.
    """
    if os.path.exists(SESSION_FILE):
        print("[*] Found saved session. Attempting to load...")
        try:
            with open(SESSION_FILE, "r") as f:
                session_string = f.read().strip()
            
            client = Client(
                name="swarm_account",
                session_string=session_string,
                in_memory=True
            )
            await client.start()
            me = await client.get_me()
            print(f"  [+] Loaded session: @{me.username or me.id} (ID: {me.id})")
            return client
        except Exception as e:
            print(f"  [!] Saved session invalid or expired: {e}")
            print("  [!] Will re-login.\n")
            if os.path.exists(SESSION_FILE):
                os.remove(SESSION_FILE)
    
    # --- First-time login flow ---
    print("\n" + "="*50)
    print("  FIRST-TIME LOGIN")
    print("="*50)
    print("\nYou need to log in with your Telegram account.")
    print("This script will use YOUR account to send reports.")
    print("⚠️  Your account may get rate-limited or banned.")
    print("    Proceed only if you understand the risk.\n")
    
    api_id = input("Enter your API ID (from my.telegram.org): ").strip()
    api_hash = input("Enter your API HASH (from my.telegram.org): ").strip()
    
    if not api_id or not api_hash:
        print("[!] API credentials required. Get them at https://my.telegram.org/apps")
        return None
    
    try:
        api_id = int(api_id)
    except ValueError:
        print("[!] API ID must be a number.")
        return None
    
    client = Client(name="swarm_login", api_id=api_id, api_hash=api_hash, in_memory=True)
    await client.start()
    
    phone = input("Enter your phone number (with country code, e.g. +1234567890): ").strip()
    sent_code = await client.send_code(phone)
    
    code = input("Enter the code Telegram sent you: ").strip()
    try:
        await client.sign_in(phone, sent_code.phone_code_hash, code)
    except Exception as e:
        print(f"[!] Login failed: {e}")
        if "Two-factor" in str(e) or "password" in str(e).lower():
            password = input("Enter your 2FA password: ").strip()
            await client.check_password(password)
        else:
            return None
    
    me = await client.get_me()
    print(f"\n  [+] Logged in as @{me.username or me.id} (ID: {me.id})")
    
    session_string = await client.export_session_string()
    with open(SESSION_FILE, "w") as f:
        f.write(session_string)
    print(f"  [+] Session saved to {SESSION_FILE}")
    
    return client


async def run_swarm():
    """Coordinate mass reporting with one or more sessions."""
    
    print(f"""
╔══════════════════════════════════════════╗
║    TELEGRAM MASS REPORT SWARM            ║
║    By: Dev Shazam                        ║
║    Target: @{TARGET_USERNAME}                     ║
║    Target runtime: {TOTAL_RUNTIME//60} min               ║
╚══════════════════════════════════════════╝
    """)
    
    # --- Step 1: Login or load saved session ---
    primary_client = await login_or_load()
    if not primary_client:
        print("[!] Could not authenticate. Exiting.")
        return
    
    clients = [primary_client]
    
    # --- Step 2: Optionally load additional sessions from ./sessions/ ---
    session_files = get_session_files(SESSION_DIR, SESSION_PATTERN)
    if session_files:
        print(f"\n[*] Found {len(session_files)} additional session files in {SESSION_DIR}")
        for sess in session_files:
            client = await create_client(sess)
            if client:
                clients.append(client)
        print(f"[*] Total sessions: {len(clients)}")
    else:
        print(f"\n[*] No additional session files found in {SESSION_DIR}/")
        print("    Running with 1 session. Add more .session files for more firepower.")
    
    # --- Step 3: Resolve target ---
    target_id = await resolve_target(clients[0], TARGET_USERNAME)
    if not target_id:
        print(f"[!] Could not resolve target @{TARGET_USERNAME}")
        for c in clients:
            await c.stop()
        return
    
    # --- Step 4: Main loop ---
    end_time = time.time() + TOTAL_RUNTIME
    round_num = 0
    total_sent = 0
    total_failed = 0
    
    print(f"\n[*] Starting mass report against @{TARGET_USERNAME} (ID: {target_id})")
    print(f"[*] Will run until {datetime.fromtimestamp(end_time).strftime('%H:%M:%S')}")
    print(f"[*] Using {len(REPORT_CHATS)} report destinations")
    print(f"[*] {REPORTS_PER_SESSION} reports per destination per session\n")
    
    while time.time() < end_time:
        round_num += 1
        print(f"\n{'='*50}")
        print(f"[*] Round {round_num} starting — {len(clients)} sessions active")
        print(f"{'='*50}")
        
        tasks = []
        for client in clients:
            task = asyncio.create_task(report_cycle(client, target_id, REPORT_CHATS))
            tasks.append(task)
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        round_sent = 0
        round_failed = 0
        for r in results:
            if isinstance(r, dict):
                round_sent += r["sent"]
                round_failed += r["failed"]
        
        total_sent += round_sent
        total_failed += round_failed
        
        print(f"\n[✓] Round {round_num} complete")
        print(f"    Reports sent this round: {round_sent}")
        print(f"    Failed: {round_failed}")
        print(f"    Total sent so far: {total_sent}")
        print(f"    Total failed: {total_failed}")
        
        alive = [c for c in clients if c.is_connected]
        if len(alive) < len(clients):
            print(f"[!] {len(clients) - len(alive)} sessions died. Continuing with {len(alive)}")
            clients = alive
        
        if not clients:
            print("[!] All sessions dead. Aborting.")
            break
        
        remaining = end_time - time.time()
        print(f"    Time remaining: {int(remaining // 60)}m {int(remaining % 60)}s")
        
        if remaining > 0:
            delay = random.uniform(ROUND_DELAY_MIN, ROUND_DELAY_MAX)
            print(f"    Next round in {delay:.0f}s...")
            await asyncio.sleep(min(delay, remaining))
    
    elapsed = TOTAL_RUNTIME - (end_time - time.time())
    print(f"\n{'='*50}")
    print(f"[*] SWARM COMPLETE")
    print(f"[*] Ran for {elapsed//60:.0f}m {elapsed%60:.0f}s")
    print(f"[*] Total reports sent: {total_sent}")
    print(f"[*] Total failed: {total_failed}")
    print(f"[*] Target: @{TARGET_USERNAME} (ID: {target_id})")
    print(f"[*] By: Dev Shazam")
    print(f"{'='*50}")
    
    for c in clients:
        await c.stop()
    print("\n[*] All sessions stopped.")


if __name__ == "__main__":
    print("[*] Initializing Telegram Mass Report Swarm...")
    print("[*] By: Dev Shazam")
    print("[*] Press Ctrl+C to abort at any time\n")
    
    try:
        asyncio.run(run_swarm())
    except KeyboardInterrupt:
        print("\n\n[!] Aborted by user.")
    except Exception as e:
        print(f"\n[x] Fatal error: {e}")
        import traceback
        traceback.print_exc()

