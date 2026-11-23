import json
import random
import time
from pathlib import Path

from adb import device_capture_screen, device_connect, device_reset_app, device_tap
from actions import (
    accept_congratulations,
    accept_daily_checkin,
    accept_daily_checkin_boost_set,
    accept_daily_new,
    accept_daily_treasure,
    accept_enter_league,
    accept_league_results,
    accept_level_up,
    accept_mystery_box,
    accept_overtake_break_score,
    accept_previous_rank_results,
    accept_relic_claim,
    accept_too_many_treasures,
    close_announcement_dialog,
    complete_finish,
    handle_anti_bot,
    handle_inactive,
    handle_quick_receive_and_send_lives,
    handle_send_friend_life,
    open_relic_complete,
    play_game,
    purchase_cookie_relay,
    purchase_desired_random_boost,
    purchase_fast_start,
    start_game,
    using_cookie_relay,
    using_fast_start,
)
from config import (
    BOOST_17P_BASE_SPEED_TEMPLATE,
    BOOST_15P_SCORE_BONUS_TEMPLATE,
    BOOST_20P_HP_FROM_POTIONS_TEMPLATE,
    BOOST_2PIT_LIFTS_TEMPLATE,
    BOOST_70P_CRUSH_CHANCE_TEMPLATE,
    BOOST_DOUBLE_COINS_TEMPLATE,
    BOOST_GOLD_COIN_MAGIC_TEMPLATE,
    BOOST_M15P_HP_DRAIN_TEMPLATE,
    BOOST_M30P_COLLISION_DAMAGE_TEMPLATE,
    BOOST_MAGNETIC_AURA_TEMPLATE,
    BOOST_REVIVE_ONCE_WITH_80HP_TEMPLATE,
    CONNECTION_LOST_RELOAD_BUTTON,
    DETECTION_ALWAYS_STAGES,
    DETECTION_GROUPS,
    DETECTION_RECOVERY_SCAN_INTERVAL,
    DEVICE_IP,
    DEVICE_PORT,
    SESSION_RESET_INTERVAL,
    LIVES_INTERVAL,
    UI_NEXT_ROUND_DELAY,
)
from detection import detect_stage, load_templates
from run_statistics import RunStatistics, write_json
from box_results import ResultConnectionLost, read_result_screen
from box_types import read_box_types
from startup_updates import StartupUpdates
from opening_jumps import OpeningJumps
from gift_draw import draw_gifts, gift_main_menu, gift_pick_position, wait_for_screen

# -------------------
# BOT OPTIONS
# -------------------
BOOST_CHOICES = [
    ("Double Coins",            BOOST_DOUBLE_COINS_TEMPLATE),
    ("+15% Score Bonus",        BOOST_15P_SCORE_BONUS_TEMPLATE),
    ("-15% HP Drain",           BOOST_M15P_HP_DRAIN_TEMPLATE),
    ("Revive Once with 80 HP",  BOOST_REVIVE_ONCE_WITH_80HP_TEMPLATE),
    ("70% Crush Chance",        BOOST_70P_CRUSH_CHANCE_TEMPLATE),
    ("+17% Base Speed",         BOOST_17P_BASE_SPEED_TEMPLATE),
    ("Gold Coin Magic",         BOOST_GOLD_COIN_MAGIC_TEMPLATE),
    ("-30% Collision Damage",   BOOST_M30P_COLLISION_DAMAGE_TEMPLATE),
    ("+20% HP from Potions",    BOOST_20P_HP_FROM_POTIONS_TEMPLATE),
    ("Magnetic Aura",           BOOST_MAGNETIC_AURA_TEMPLATE),
    ("2 Pit Lifts",             BOOST_2PIT_LIFTS_TEMPLATE),
]
SETTINGS_PATH = Path(__file__).with_name('last_settings.json')


def save_options(path, options):
    write_json(path, {key: value for key, value in options.items()
                      if key not in ('desired_boost_template', 'run_mode')})


def get_detection_stage_names(group_name, exclude=None):
    stage_names = []
    # For non-in-game groups, always stages have higher priority
    if group_name != "IN_GAME":
        for stage_name in DETECTION_ALWAYS_STAGES:
            if stage_name not in stage_names:
                stage_names.append(stage_name)
    # Add stages from the specified detection group
    for stage_name in DETECTION_GROUPS[group_name]:
        if stage_name not in stage_names:
            stage_names.append(stage_name)
    # For in-game, always stages are appended last (original behavior)
    if group_name == "IN_GAME":
        for stage_name in DETECTION_ALWAYS_STAGES:
            if stage_name not in stage_names:
                stage_names.append(stage_name)
    if exclude:
        stage_names = [s for s in stage_names if s not in exclude]
    return stage_names


def load_saved_options(path):
    try:
        saved = json.loads(path.read_text(encoding='utf-8'))
        flags = ('use_fast_start', 'use_cookie_relay',
                 'use_desired_random_boost', 'detect_relic')
        if not isinstance(saved, dict) or any(type(saved.get(key)) is not bool for key in flags):
            raise ValueError('Invalid saved options')
        options = {key: saved[key] for key in flags}
        options['jump_at_start'] = saved.get('jump_at_start') is True
        gift_limit = saved.get('gift_limit', 1)
        options['gift_limit'] = gift_limit if type(gift_limit) is int and 1 <= gift_limit <= 9999 else 1
        round_limit = saved.get('round_limit', 0)
        options['round_limit'] = round_limit if type(round_limit) is int and round_limit >= 0 else 0
        boost_name = saved.get('desired_boost_name') if options['use_desired_random_boost'] else None
        choices = dict(BOOST_CHOICES)
        if options['use_desired_random_boost'] and (
            not isinstance(boost_name, str) or boost_name not in choices
        ):
            raise ValueError('Unknown saved boost')
        options['desired_boost_name'] = boost_name
        options['desired_boost_template'] = choices.get(boost_name)
        return options
    except FileNotFoundError:
        return None
    except (OSError, ValueError):
        print('Saved settings could not be read. Please choose your settings again.')
        return None


def prompt_user_options(settings_path=None):
    path = Path(settings_path) if settings_path is not None else SETTINGS_PATH
    saved = load_saved_options(path)
    if saved is not None:
        print('Last saved settings')
        for label, key in [('Fast Start', 'use_fast_start'), ('Cookie Relay', 'use_cookie_relay')]:
            print(f'{label}: {"On" if saved[key] else "Off"}')
        print(f'Random Boost: {saved["desired_boost_name"] or "Off"}')
        print(f'Claim Relics: {"On" if saved["detect_relic"] else "Off"}')
        while True:
            choice = input('Use these settings? [y/n]: ').strip().lower()
            if choice in ('', 'y', 'yes'):
                return saved
            if choice in ('n', 'no'):
                break
            print('Please enter Y or N.')

    desired_boost_template = None
    desired_boost_name = None

    print("⚙️ --- Bot Options ---")
    use_fast_start = input("⚡ Use Fast Start (buy + use)? [y/n]: ").strip().lower() == "y"
    use_cookie_relay = input("🍪 Use Cookie Relay (buy + use)? [y/n]: ").strip().lower() == "y"
    use_desired_random_boost = input("🎲 Use Desired Random Boost (buy + use)? [y/n]: ").strip().lower() == "y"
    if use_desired_random_boost:
        print("  Select desired boost (must match the boost option configured in-game):")
        for i, (name, _) in enumerate(BOOST_CHOICES, 1):
            print(f"  {i:2}. {name}")
        while True:
            choice = input("  Enter number: ").strip()
            if choice.isdigit() and 1 <= int(choice) <= len(BOOST_CHOICES):
                desired_boost_template = BOOST_CHOICES[int(choice) - 1][1]
                desired_boost_name = BOOST_CHOICES[int(choice) - 1][0]
                print(f"  ✅ Selected: {desired_boost_name}")
                break
            print(f"  ⚠️ Please enter a number between 1 and {len(BOOST_CHOICES)}.")
    detect_relic = input("🏺 Detect Relic (open + claim)? [y/n]: ").strip().lower() == "y"
    print("---------------------")

    options = {
        "use_fast_start": use_fast_start,
        "use_cookie_relay": use_cookie_relay,
        "use_desired_random_boost": use_desired_random_boost,
        "desired_boost_template": desired_boost_template,
        "desired_boost_name": desired_boost_name if use_desired_random_boost else None,
        "detect_relic": detect_relic,
        "jump_at_start": False,
        "round_limit": 0,
    }
    try:
        save_options(path, options)
    except OSError:
        print('Could not save settings. Using your selections for this session.')
    return options


# -------------------
# MAIN LOOP
# -------------------
def recover_game_connection(wait, on_status, updates):
    max_attempts = 2
    for attempt in range(1, max_attempts + 1):
        if on_status:
            on_status(f'Reconnecting ({attempt}/{max_attempts})')
        print(f'🔌 Connection lost. Tapping Confirm ({attempt}/{max_attempts}).')
        device_tap(DEVICE_IP, DEVICE_PORT, *CONNECTION_LOST_RELOAD_BUTTON)

        for check in range(15):
            wait(2)
            screen = device_capture_screen(DEVICE_IP, DEVICE_PORT)
            stage = detect_stage(screen, ['ANTI_BOT', 'MAINMENU'])
            if stage == 'ANTI_BOT':
                raise RuntimeError('Player verification required. Complete it in LDPlayer, then start again.')
            if updates.dismiss_popup(screen):
                continue
            if stage == 'MAINMENU':
                print('✅ Connection restored. Back at the main menu.')
                if on_status:
                    on_status('Connection restored')
                return
            if check % 5 == 0 and updates.check_login_during_reconnect(screen):
                return

        if not detect_stage(screen, ['CONNECTION_LOST']):
            break

    raise RuntimeError('Connection lost. The game did not return to the main menu. Check LDPlayer, then start again.')



def main(options=None, *, stop=None, on_status=None, statistics_factory=None, on_error=None):
    statistics = None
    interactive_window = stop is not None

    def wait(seconds):
        if stop is None:
            time.sleep(seconds)
        elif stop.wait(seconds):
            raise KeyboardInterrupt

    try:
        print("🚀 cookierun-classic-autorun started")
        print("⚠️ Screen must be 1280x720 resolution for the bot to work properly.")
        print(f"📱 Connecting to device at {DEVICE_IP}:{DEVICE_PORT}...")

        device_connect(DEVICE_IP, DEVICE_PORT)
        load_templates()

        if options is None:
            options = prompt_user_options()
        mode = options.get('run_mode', 'auto') if interactive_window else 'auto'
        if mode == 'auto':
            statistics = (statistics_factory or RunStatistics)()
        round_limit = options.get('round_limit', 0) if interactive_window else 0
        if on_status:
            on_status('Running')
        updates = StartupUpdates()
        if statistics is not None:
            print('📊 Statistics are saved in stats/summary.txt and stats/sessions/.')
        relic_exclude = None if options["detect_relic"] else {"RELIC_COMPLETE", "RELIC_CLAIM"}

        last_stage = None
        is_first_game = True
        detection_group = "PRE_GAME"
        last_detected_time = time.time()
        session_start_time = time.time()
        session_reset_interval = random.uniform(*SESSION_RESET_INTERVAL)
        last_lives_time = time.time()
        lives_interval = LIVES_INTERVAL
        pending_send_friend_life = False
        opening_jumps = None

        while stop is None or not stop.is_set():
            device_screen = device_capture_screen(DEVICE_IP, DEVICE_PORT)
            if interactive_window and detect_stage(device_screen, ['ANTI_BOT']):
                raise RuntimeError('Player verification required. Complete it in LDPlayer, then start again.')
            if detection_group != 'IN_GAME' and updates.dismiss_popup(device_screen):
                last_stage = None
                wait(1)
                continue
            stage = detect_stage(device_screen, get_detection_stage_names(detection_group, exclude=relic_exclude))
            if mode != 'auto' and stage != 'CONNECTION_LOST':
                if gift_main_menu(device_screen):
                    stage = 'MAINMENU'
                elif mode == 'gifts' and gift_pick_position(device_screen):
                    stage = 'GIFT_PICK'
            if updates.login_required:
                if stage != 'MAINMENU':
                    wait(2)
                    continue
                updates.login_required = False
            if stage is None:
                if time.time() - last_detected_time >= DETECTION_RECOVERY_SCAN_INTERVAL[detection_group]:
                    stage = detect_stage(device_screen, exclude=relic_exclude)
                    last_detected_time = time.time()
            else:
                last_detected_time = time.time()

            if stage in ('MAINMENU', 'GAME_RELAY', 'GAME_COMPLETE', 'CONNECTION_LOST'):
                opening_jumps = None
            if stage is None and opening_jumps is not None:
                if opening_jumps.observe(device_screen, wait):
                    opening_jumps = None
                wait(0.20)
                continue

            if stage is None and updates.handle_if_needed(device_screen):
                if updates.login_required and on_status:
                    on_status('กรุณา Login')
                last_stage = None
                detection_group = 'PRE_GAME'
                continue

            if mode != 'auto' and stage not in ('MAINMENU', 'GIFT_PICK', 'CONNECTION_LOST'):
                if last_stage != 'waiting-for-menu' and on_status:
                    on_status('Waiting for Main Menu')
                last_stage = 'waiting-for-menu'
                wait(1)
                continue

            if stage == last_stage:
                wait(0.1)
                continue

            last_stage = stage
            if on_status and stage:
                on_status(stage.replace('_', ' ').title())

            if stage in ("MAINMENU", "GIFT_PICK"):
                updates.popup_closes = 0
                if mode == 'gifts':
                    if on_status:
                        on_status('Opening Gifts')
                    opened = draw_gifts(options['gift_limit'], wait, device_screen, on_status=on_status)
                    return f'Gift Draw Finished · {opened} Opened'
                if mode == 'hearts':
                    if on_status:
                        on_status('Sending Hearts')
                    def heartbeat_progress(count):
                        if on_status:
                            on_status(f'Hearts Sent · {count}')

                    completed = handle_send_friend_life(
                        on_progress=heartbeat_progress, until_exhausted=True, wait=wait)
                    if not completed:
                        raise RuntimeError('Heart sending could not continue. Check LDPlayer and the Activity Log.')
                    wait_for_screen(wait, lambda screen: True if (
                        detect_stage(screen, ['MAINMENU']) == 'MAINMENU' or gift_main_menu(screen)
                    ) else None, 'the main menu', activity='Send Hearts')
                    return 'Heart Sending Complete'
                statistics.leave_round()
                if round_limit and statistics.session['summary']['completed'] >= round_limit:
                    print(f'Round limit reached: {round_limit} completed. Stopping at the main menu.')
                    return f'Stopped · Round limit reached ({round_limit})'
                print("🎮 Detected Stage: MAINMENU")
                # Wait screen refresh
                print("⏳ Waiting 5 seconds for screen refresh...")
                wait(5)
                if pending_send_friend_life:
                    print("💌 Sending friend lives after app reset...")
                    handle_send_friend_life()
                    pending_send_friend_life = False
                    last_lives_time = time.time()
                    last_stage = None
                    continue
                elapsed = time.time() - session_start_time
                if not interactive_window and elapsed >= session_reset_interval:
                    print(f"🔄 Session reset triggered after {elapsed / 3600:.2f}h — restarting app...")
                    device_reset_app(DEVICE_IP, DEVICE_PORT,
                                     startup_handler=lambda: updates.handle_if_needed(force=True))
                    wait(5)
                    close_announcement_dialog()
                    pending_send_friend_life = time.time() - last_lives_time >= lives_interval
                    session_start_time = time.time()
                    session_reset_interval = random.uniform(*SESSION_RESET_INTERVAL)
                    detection_group = "PRE_GAME"
                    last_stage = None
                    is_first_game = True
                    continue
                lives_elapsed = time.time() - last_lives_time
                if lives_elapsed >= lives_interval:
                    print(f"💌 Heart interval reached ({lives_elapsed / 60:.1f} min) — receiving and sending lives...")
                    handle_quick_receive_and_send_lives()
                    last_lives_time = time.time()
                    last_stage = None
                    continue
                if detection_group == "POST_GAME":
                    detection_group = "PRE_GAME"
                    last_stage = None
                    continue
                if not is_first_game:
                    delay = UI_NEXT_ROUND_DELAY if interactive_window else random.uniform(10, 30)
                    print(f"⏳ Waiting for {delay:.2f} seconds before starting the next game...")
                    if on_status:
                        on_status('Waiting for next round')
                    wait(delay)
                is_first_game = False
                start_game()
                detection_group = "PRE_GAME"
            elif stage == "PURCHASE_ITEM":
                print("🛒 Detected Stage: PURCHASE_ITEM")
                if options["use_fast_start"]:
                    purchase_fast_start()
                if options["use_cookie_relay"]:
                    purchase_cookie_relay()
                if options["use_desired_random_boost"]:
                    purchase_desired_random_boost(options["desired_boost_template"], options["desired_boost_name"])
                play_game()
                statistics.begin()
                if interactive_window and options.get('jump_at_start'):
                    opening_jumps = OpeningJumps(time.monotonic() + 18, options['use_fast_start'])
                detection_group = "IN_GAME"
                wait(0.2)
                last_stage = None
            elif stage == "GAME_START":
                statistics.begin()
                print("🏁 Detected Stage: GAME_START")
                if options["use_fast_start"]:
                    using_fast_start()
                    if opening_jumps is not None:
                        opening_jumps.activated = True
                        print('Opening jumps: waiting for Fast Start to finish.')
                detection_group = "IN_GAME"
            elif stage == "GAME_RELAY":
                print("🔄 Detected Stage: GAME_RELAY")
                if options["use_cookie_relay"]:
                    using_cookie_relay()
                detection_group = "IN_GAME"
            elif stage == "GAME_COMPLETE":
                print("✅ Detected Stage: GAME_COMPLETE")
                try:
                    capture_round_result(statistics, device_screen, wait)
                except ResultConnectionLost:
                    detection_group = "POST_GAME"
                    last_stage = None
                    continue
                complete_finish()
                detection_group = "POST_GAME"
            elif stage == "MYSTERY_BOX":
                print("🎁 Detected Stage: MYSTERY_BOX")
                try:
                    capture_box_types(statistics)
                except ResultConnectionLost:
                    detection_group = "POST_GAME"
                    last_stage = None
                    continue
                accept_mystery_box()
                wait(3)
                detection_group = "POST_GAME"
                last_stage = None
            elif stage == "CONGRATULATIONS":
                print("🎉 Detected Stage: CONGRATULATIONS")
                accept_congratulations()
                detection_group = "POST_GAME"
                last_stage = None
            elif stage == "LEVEL_UP":
                print("⬆️ Detected Stage: LEVEL_UP")
                accept_level_up()
                detection_group = "PRE_GAME"
            elif stage == "DAILY_CHECKIN":
                print("📅 Detected Stage: DAILY_CHECKIN")
                accept_daily_checkin()
                detection_group = "PRE_GAME"
            elif stage == "DAILY_CHECKIN_BOOST_SET":
                print("📅 Detected Stage: DAILY_CHECKIN_BOOST_SET")
                accept_daily_checkin_boost_set()
                detection_group = "PRE_GAME"
            elif stage == "DAILY_TREASURE":
                print("💎 Detected Stage: DAILY_TREASURE")
                accept_daily_treasure()
                detection_group = "PRE_GAME"
            elif stage == "DAILY_NEW":
                print("📰 Detected Stage: DAILY_NEW")
                accept_daily_new()
                detection_group = "PRE_GAME"
            elif stage == "ENTER_LEAGUE":
                print("🏆 Detected Stage: ENTER_LEAGUE")
                accept_enter_league()
                detection_group = "PRE_GAME"
            elif stage == "LEAGUE_RESULTS":
                print("🏆 Detected Stage: LEAGUE_RESULTS")
                accept_league_results()
                detection_group = "PRE_GAME"
            elif stage == "PREVIOUS_RANK_RESULTS":
                print("🏆 Detected Stage: PREVIOUS_RANK_RESULTS")
                accept_previous_rank_results()
                detection_group = "PRE_GAME"
            elif stage == "OVERTAKE_BREAK_SCORE":
                print("🏆 Detected Stage: OVERTAKE_BREAK_SCORE")
                accept_overtake_break_score()
                detection_group = "POST_GAME"
                last_stage = None
            elif stage == "TOO_MANY_TREASURES":
                print("💎 Detected Stage: TOO_MANY_TREASURES")
                accept_too_many_treasures()
                detection_group = "PRE_GAME"
            elif stage == "RELIC_COMPLETE":
                print("🏺 Detected Stage: RELIC_COMPLETE")
                open_relic_complete()
                detection_group = "PRE_GAME"
            elif stage == "RELIC_CLAIM":
                print("🏺 Detected Stage: RELIC_CLAIM")
                accept_relic_claim()
                detection_group = "PRE_GAME"
            elif stage == "ANTI_BOT":
                if interactive_window:
                    raise RuntimeError('Player verification required. Complete it in LDPlayer, then start again.')
                print("⚠️ Detected Stage: ANTI_BOT")
                handle_anti_bot(device_screen)
                last_stage = None
            elif stage == "CONNECTION_LOST":
                print("🔌 Detected Stage: CONNECTION_LOST")
                if statistics is not None:
                    statistics.leave_round('Connection lost before a result was observed')
                if interactive_window:
                    recover_game_connection(wait, on_status, updates)
                    if updates.login_required and on_status:
                        on_status('กรุณา Login')
                    detection_group = 'PRE_GAME'
                    last_stage = None
                    is_first_game = True
                    continue
                device_reset_app(DEVICE_IP, DEVICE_PORT,
                                 startup_handler=lambda: updates.handle_if_needed(force=True))
                wait(5)
                close_announcement_dialog()
                session_start_time = time.time()
                session_reset_interval = random.uniform(*SESSION_RESET_INTERVAL)
                detection_group = "PRE_GAME"
                last_stage = None
                is_first_game = True
            elif stage == "INACTIVE":
                print("💤 Detected Stage: INACTIVE")
                handle_inactive()
                last_stage = None
            wait(0.25)
    except KeyboardInterrupt:
        if interactive_window:
            return 'Stopped by User'
        print("🛑 Bot stopped by user.")
    except Exception as e:
        if interactive_window:
            if on_error is not None:
                on_error(e)
            raise
        print(f"❌ An error occurred: {e}")
    finally:
        if statistics is not None:
            statistics.close()


def capture_round_result(statistics, screen, wait=None):
    if statistics.current is not None and statistics.current['status'] == 'completed':
        return
    count, evidence, rewards = read_result_screen(screen)
    if wait is not None:
        wait(0)
    statistics.complete()
    statistics.record_rewards(rewards)
    missing = [label for name, label in (('coins', 'Coins'), ('exp', 'EXP')) if name not in rewards]
    if missing:
        print(f'⚠️ {", ".join(missing)} could not be confirmed on the settled result screen.')
    if count is None:
        statistics.current['box_source'] = evidence
        statistics.current['note'] = 'Box counter was not stable or readable on the result screen.'
        statistics.save()
        print('⚠️ Result box count unreadable. Checking the Mystery Box screen if it appears.')
        print(f'📸 Result screenshot saved: {evidence}')
    else:
        statistics.record_boxes(count, evidence)
        if count == 0:
            statistics.print_round()


def capture_box_types(statistics):
    current = statistics.current
    if current is None or current['status'] != 'completed':
        return
    if current.get('box_types') is not None or current['boxes'] == 0:
        return
    counts, evidence = read_box_types(current['boxes'])
    if counts is None:
        print(f'⚠️ Mystery Boxes could not be confirmed. Screenshot: {evidence}')
        return
    if current['boxes'] is None:
        count = sum(counts.values())
        statistics.record_boxes(count, evidence)
        print(f'✅ Box count recovered from the Mystery Box screen: {count}.')
    statistics.record_box_types(counts, evidence)
    statistics.print_round()
