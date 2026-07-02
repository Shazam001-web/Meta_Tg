
# ========================================================================
# SINGLE-ACCOUNT LOGIN + SWARM LAUNCH
# ========================================================================

import sys
import json
from pathlib import Path

SESSION_FILE = "session_string.txt"  # Stores the logged-in session as a string

async def login_or_load() -> Optional[Client]:
    """
    First-run: prompt for API credentials + phone + OTP.
    Subsequent runs: load saved string session.
    Returns an authenticated Client.
    """
    # If we already have a saved session, try to load it
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
            os.remove(SESSION_FILE)  # Clean up bad session
    
    # --- First-time login flow ---
    print("\n" + "="*50)
    print("  FIRST-TIME LOGIN")
    print("="*50)
    print("\nYou need to log in with your Telegram account.")
    print("This script will use YOUR account to send reports.")
    print("⚠️  Your account may get rate-limited or banned.")
    print("    Proceed only if you understand the risk.\n")
    
    # Get API credentials
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
    
    # Create temporary client to log in
    client = Client(
        name="swarm_login",
        api_id=api_id,
        api_hash=api_hash,
        in_memory=True
    )
    
    await client.start()
    
    # Send code
    phone = input("Enter your phone number (with country code, e.g. +1234567890): ").strip()
    sent_code = await client.send_code(phone)
    
    # Wait for OTP
    code = input("Enter the code Telegram sent you: ").strip()
    try:
        await client.sign_in(phone, sent_code.phone_code_hash, code)
    except Exception as e:
        print(f"[!] Login failed: {e}")
        # Maybe 2FA?
        if "Two-factor" in str(e) or "password" in str(e).lower():
            password = input("Enter your 2FA password: ").strip()
            await client.check_password(password)
        else:
            return None
    
    me = await client.get_me()
    print(f"\n  [+] Logged in as @{me.username or me.id} (ID: {me.id})")
    
    # Save session string for future runs
    session_string = await client.export_session_string()
    with open(SESSION_FILE, "w") as f:
        f.write(session_string)
    print(f"  [+] Session saved to {SESSION_FILE}")
    
    return client


async def run_swarm():
    """Coordinate mass reporting with one or more sessions."""
    
    print(f"""
╔══════════════════════════════════════╗
║    TELEGRAM MASS REPORT       ║By: Dev shazam
║    Target: @{TARGET_USERNAME}               ║
║    Target runtime: {TOTAL_RUNTIME//60} min         ║
╚══════════════════════════════════════╝
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
            proxy = None  # You can add proxy logic here if needed
            client = await create_client(sess, proxy)
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
        round_start = time.time()
        print(f"\n{'='*50}")
        print(f"[*] Round {round_num} starting — {len(clients)} sessions active")
        print(f"{'='*50}")
        
        # Run report cycles for all sessions concurrently
        tasks = []
        for client in clients:
            task = asyncio.create_task(
                report_cycle(client, target_id, REPORT_CHATS,
                            f"session_{clients.index(client)}")
            )
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
        
        # Session health check
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
            if len(clients) < len(session_files) // 2:
                delay *= 0.5
            print(f"    Next round in {delay:.0f}s...")
            await asyncio.sleep(min(delay, remaining))
    
    # Summary
    elapsed = TOTAL_RUNTIME - (end_time - time.time())
    print(f"\n{'='*50}")
    print(f"[*] SWARM COMPLETE")
    print(f"[*] Ran for {elapsed//60:.0f}m {elapsed%60:.0f}s")
    print(f"[*] Total reports sent: {total_sent}")
    print(f"[*] Total failed: {total_failed}")
    print(f"[*] Target: @{TARGET_USERNAME} (ID: {target_id})")
    print(f"{'='*50}")
    
    for c in clients:
        await c.stop()
    print("\n[*] All sessions stopped.")

if name == "main":
    print("[*] Initializing Telegram Mass Report Swarm...")
    print("[*] Press Ctrl+C to abort at any time\n")
    
    try:
        asyncio.run(run_swarm())
    except KeyboardInterrupt:
        print("\n\n[!] Aborted by user.")
    except Exception as e:
        print(f"\n[x] Fatal error: {e}")
        import traceback
        traceback.print_exc()
