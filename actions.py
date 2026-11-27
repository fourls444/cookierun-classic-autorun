import numpy as np
import cv2
import random
import time

from adb import safe_device_tap, safe_device_scroll, device_capture_screen
from config import (
    ACCEPT_ALL_LIVES_RECEIVED_AND_SENT_BUTTON,
    ACCEPT_CONGRATULATIONS_BUTTON,
    ACCEPT_DAILY_CHECKIN_BOOST_SET_BUTTON,
    ACCEPT_DAILY_CHECKIN_BUTTON,
    ACCEPT_DAILY_TREASURE_BUTTON,
    ACCEPT_DAILY_NEW_BUTTON,
    ACCEPT_ENTER_LEAGUE_BUTTON,
    ACCEPT_LEAGUE_RESULTS_BUTTON,
    ACCEPT_LEVEL_UP_BUTTON,
    ACCEPT_MYSTERY_BOX_BUTTON,
    ACCEPT_OVERTAKE_BREAK_SCORE_BUTTON,
    ACCEPT_PREVIOUS_RANK_RESULTS_BUTTON,
    ACCEPT_TOO_MANY_TREASURES_BUTTON,
    ALL_LIVES_RECEIVED_AND_SENT_REGION,
    ALL_LIVES_RECEIVED_AND_SENT_TEMPLATE,
    CLOSE_ANNOUNCEMENT_DIALOG_BUTTON,
    CLOSE_SEND_LIFE_DIALOG_BUTTON,
    COMPLETE_FINISH_BUTTON,
    CONFIRM_SEND_LIFE_BUTTON,
    CONFIRM_SEND_LIFE_REGION,
    CONFIRM_SEND_LIFE_TEMPLATE,
    COOKIE_RELAY_ITEM,
    COOKIE_RELAY_USE_BUTTON,
    LIVES_MAX_TOP_SCROLLS,
    LIVES_MAX_DOWN_SCROLLS,
    LIVES_MAX_EMPTY_SCROLLS,
    LIVES_TIMEOUT,
    EXIT_GAME_SETTINGS_BUTTON,
    EXIT_PARTY_RUN_MODE_BUTTON,
    FAST_START_ITEM,
    FAST_START_USE_BUTTON,
    FRIEND_BOTTOM_LEADERBOARD_REGION,
    FRIEND_BOTTOM_LEADERBOARD_TEMPLATE,
    FRIEND_LIST_SWIPE_CENTER,
    FRIEND_SEND_LIFE_REGION,
    FRIEND_SEND_LIFE_TEMPLATE,
    FRIEND_TOP_LEADERBOARD_REGION,
    FRIEND_TOP_LEADERBOARD_TEMPLATE,
    INACTIVE_RELOAD_BUTTON,
    LEADERBOARD_BOTTOM_POSITION,
    LEADERBOARD_TOP_POSITION,
    MAIL_BOX_BUTTON,
    MAIL_BOX_LIVES_TAB_BUTTON,
    MAIL_BOX_CLOSE_BUTTON,
    MULTI_BUY_BUTTON,
    MULTI_PURCHASE_BUTTON,
    NO_LIVES_TO_RECEIVE_REGION,
    NO_LIVES_TO_RECEIVE_TEMPLATE,
    PLAY_BUTTON,
    PURCHASE_BUTTON,
    QUICK_RECEIVE_AND_SEND_LIVES_BUTTON,
    RANDOM_BOOST_ITEM,
    RANDOM_BOOST_REGION,
    RELIC_CLAIM_BUTTON,
    RELIC_CLOSE_BUTTON,
    RELIC_COMPLETE_BUTTON,
    START_BUTTON,
    CONNECTION_LOST_RELOAD_BUTTON,
)
from detection import detect_templates, detect_anti_bot_odd_cards, detect_stage
from startup_updates import StartupUpdates
from config import (
    ANTI_BOT_CARD_POS_1, ANTI_BOT_CARD_POS_2, ANTI_BOT_CARD_POS_3,
    ANTI_BOT_CARD_POS_4, ANTI_BOT_CARD_POS_5, ANTI_BOT_CARD_POS_6,
    ANTI_BOT_CARD_WIDTH, ANTI_BOT_CARD_HEIGHT,
)

def start_game():
    print("🏁 Starting the game...")
    safe_device_tap(START_BUTTON[0], START_BUTTON[1])
    time.sleep(random.uniform(0.35, 0.6))


def play_game():
    print("🎮 Playing the game...")
    safe_device_tap(PLAY_BUTTON[0], PLAY_BUTTON[1])
    time.sleep(random.uniform(0.35, 0.6))


def purchase_fast_start():
    print("🛒 Purchasing Fast Start...")
    safe_device_tap(FAST_START_ITEM[0], FAST_START_ITEM[1])
    time.sleep(random.uniform(0.35, 0.6))
    safe_device_tap(PURCHASE_BUTTON[0], PURCHASE_BUTTON[1])
    time.sleep(random.uniform(0.5, 0.8))


def purchase_cookie_relay():
    print("🛒 Purchasing Cookie Relay...")
    safe_device_tap(COOKIE_RELAY_ITEM[0], COOKIE_RELAY_ITEM[1])
    time.sleep(random.uniform(0.35, 0.6))
    safe_device_tap(PURCHASE_BUTTON[0], PURCHASE_BUTTON[1])
    time.sleep(random.uniform(0.5, 0.8))


def purchase_random_boost():
    print("🛒 Purchasing Random Boost...")
    safe_device_tap(RANDOM_BOOST_ITEM[0], RANDOM_BOOST_ITEM[1])
    time.sleep(random.uniform(0.35, 0.6))
    safe_device_tap(PURCHASE_BUTTON[0], PURCHASE_BUTTON[1])
    time.sleep(random.uniform(0.5, 0.8))


def purchase_desired_random_boost(desired_template, desired_name):
    print("🛒 Purchasing Desired Random Boost...")
    safe_device_tap(RANDOM_BOOST_ITEM[0], RANDOM_BOOST_ITEM[1])
    time.sleep(random.uniform(0.35, 0.6))
    safe_device_tap(MULTI_PURCHASE_BUTTON[0], MULTI_PURCHASE_BUTTON[1])
    time.sleep(random.uniform(0.5, 0.8))
    safe_device_tap(MULTI_BUY_BUTTON[0], MULTI_BUY_BUTTON[1])
    time.sleep(random.uniform(0.35, 0.6))
    print(f"🔍 Waiting for desired boost to be detected: {desired_name}...")
    timeout = 30
    start_time = time.time()
    while True:
        if time.time() - start_time > timeout:
            print(f"⏰ Timeout: Could not detect desired boost '{desired_name}' within {timeout} seconds.")
            print("⚠️ Skipping Desired Random Boost. Please verify your in-game boost config is correct.")
            return
        screen = device_capture_screen()
        if detect_templates(screen, desired_template, RANDOM_BOOST_REGION):
            print(f"✅ Desired Boost detected: {desired_name}!")
            break
        time.sleep(0.5)


def using_fast_start():
    print("⚡ Using Fast Start...")
    safe_device_tap(FAST_START_USE_BUTTON[0], FAST_START_USE_BUTTON[1])
    time.sleep(random.uniform(0.35, 0.55))


def using_cookie_relay():
    print("🍪 Using Cookie Relay...")
    safe_device_tap(COOKIE_RELAY_USE_BUTTON[0], COOKIE_RELAY_USE_BUTTON[1])
    time.sleep(random.uniform(0.35, 0.55))


def complete_finish():
    print("🏆 Completing the game...")
    safe_device_tap(COMPLETE_FINISH_BUTTON[0], COMPLETE_FINISH_BUTTON[1])
    time.sleep(random.uniform(0.35, 0.6))


def accept_mystery_box():
    print("🎁 Accepting Mystery Box...")
    safe_device_tap(ACCEPT_MYSTERY_BOX_BUTTON[0], ACCEPT_MYSTERY_BOX_BUTTON[1])
    time.sleep(random.uniform(0.35, 0.6))


def accept_congratulations():
    print("🎉 Accepting Congratulations...")
    safe_device_tap(ACCEPT_CONGRATULATIONS_BUTTON[0], ACCEPT_CONGRATULATIONS_BUTTON[1])
    time.sleep(random.uniform(0.35, 0.6))


def accept_level_up():
    print("⬆️ Accepting Level Up...")
    safe_device_tap(ACCEPT_LEVEL_UP_BUTTON[0], ACCEPT_LEVEL_UP_BUTTON[1])
    time.sleep(random.uniform(0.35, 0.6))


def accept_daily_checkin():
    print("📅 Accepting Daily Check-in...")
    safe_device_tap(ACCEPT_DAILY_CHECKIN_BUTTON[0], ACCEPT_DAILY_CHECKIN_BUTTON[1])
    time.sleep(random.uniform(0.35, 0.6))


def accept_daily_checkin_boost_set():
    print("📅 Accepting Daily Check-in Boost Set...")
    safe_device_tap(ACCEPT_DAILY_CHECKIN_BOOST_SET_BUTTON[0], ACCEPT_DAILY_CHECKIN_BOOST_SET_BUTTON[1])
    time.sleep(random.uniform(0.35, 0.6))


def accept_daily_treasure():
    print("💎 Accepting Daily Treasure...")
    safe_device_tap(ACCEPT_DAILY_TREASURE_BUTTON[0], ACCEPT_DAILY_TREASURE_BUTTON[1])
    time.sleep(random.uniform(0.35, 0.6))


def accept_daily_new():
    print("📰 Accepting Daily New...")
    safe_device_tap(ACCEPT_DAILY_NEW_BUTTON[0], ACCEPT_DAILY_NEW_BUTTON[1])
    time.sleep(random.uniform(0.35, 0.6))


def accept_enter_league():
    print("🏆 Accepting Enter League...")
    safe_device_tap(ACCEPT_ENTER_LEAGUE_BUTTON[0], ACCEPT_ENTER_LEAGUE_BUTTON[1])
    time.sleep(random.uniform(0.35, 0.6))


def accept_league_results():
    print("🏆 Accepting League Results...")
    safe_device_tap(ACCEPT_LEAGUE_RESULTS_BUTTON[0], ACCEPT_LEAGUE_RESULTS_BUTTON[1])
    time.sleep(random.uniform(0.35, 0.6))


def accept_previous_rank_results():
    print("🏆 Accepting Previous Rank Results...")
    safe_device_tap(ACCEPT_PREVIOUS_RANK_RESULTS_BUTTON[0], ACCEPT_PREVIOUS_RANK_RESULTS_BUTTON[1])
    time.sleep(random.uniform(0.35, 0.6))

def accept_too_many_treasures():
    print("💎 Accepting Too Many Treasures...")
    safe_device_tap(ACCEPT_TOO_MANY_TREASURES_BUTTON[0], ACCEPT_TOO_MANY_TREASURES_BUTTON[1])
    time.sleep(random.uniform(0.35, 0.6))

def accept_overtake_break_score():
    print("🏆 Accepting Overtake Break Score...")
    safe_device_tap(ACCEPT_OVERTAKE_BREAK_SCORE_BUTTON[0], ACCEPT_OVERTAKE_BREAK_SCORE_BUTTON[1])
    time.sleep(random.uniform(0.35, 0.6))

def open_relic_complete():
    print("🏺 Opening Relic Complete...")
    safe_device_tap(RELIC_COMPLETE_BUTTON[0], RELIC_COMPLETE_BUTTON[1])
    time.sleep(random.uniform(0.35, 0.6))


def accept_relic_claim():
    print("🏺 Accepting Relic Claim...")
    safe_device_tap(RELIC_CLAIM_BUTTON[0], RELIC_CLAIM_BUTTON[1])
    time.sleep(random.uniform(0.35, 0.6))
    safe_device_tap(RELIC_CLOSE_BUTTON[0], RELIC_CLOSE_BUTTON[1])
    time.sleep(random.uniform(10, 15))


def handle_anti_bot(screen):
    print("🤖 Solving Anti-Bot captcha...")
    card_coords = [
        ANTI_BOT_CARD_POS_1, ANTI_BOT_CARD_POS_2, ANTI_BOT_CARD_POS_3,
        ANTI_BOT_CARD_POS_4, ANTI_BOT_CARD_POS_5, ANTI_BOT_CARD_POS_6,
    ]

    odd_indices = detect_anti_bot_odd_cards(screen)
    card_nums = [i + 1 for i in odd_indices]
    print(f"🃏 Found odd cards: Card {card_nums[0]} and Card {card_nums[1]}")

    for idx in odd_indices:
        cx, cy = card_coords[idx]
        # random tap position inside the card, with a small margin
        margin = 20
        tx = random.randint(cx + margin, cx + ANTI_BOT_CARD_WIDTH - margin)
        ty = random.randint(cy + margin, cy + ANTI_BOT_CARD_HEIGHT - margin)
        print(f"  👆 Tapping Card {idx + 1} at ({tx}, {ty})")
        safe_device_tap(tx, ty)
        time.sleep(random.uniform(10, 15))

    print("✅ Anti-Bot captcha solved!")
    time.sleep(random.uniform(0.35, 0.6))


def handle_connection_lost():
    print("🔌 Handling Connection Lost...")
    safe_device_tap(CONNECTION_LOST_RELOAD_BUTTON[0], CONNECTION_LOST_RELOAD_BUTTON[1])
    time.sleep(random.uniform(10, 15))


def handle_inactive():
    print("💤 Handling Inactive state...")
    safe_device_tap(INACTIVE_RELOAD_BUTTON[0], INACTIVE_RELOAD_BUTTON[1])
    time.sleep(random.uniform(10, 15))


def heart_send_confirmed(before, after, button):
    if not isinstance(before, np.ndarray) or not isinstance(after, np.ndarray) or before.shape != after.shape:
        return False
    x, y, w, h = button
    height, width = after.shape[:2]
    left = max(0, x - 150)
    stable_row = before[y:y + h, left:x - 10]
    returned_row = after[y:y + h, left:x - 10]
    if not stable_row.size or max(cv2.mean(cv2.absdiff(stable_row, returned_row))[:3]) > 18:
        return False
    region = (max(0, x - 8), max(0, y - 8), min(width, x + w + 8), min(height, y + h + 8))
    return not detect_templates(after, FRIEND_SEND_LIFE_TEMPLATE, region)


def heart_list_moved(before, after):
    if not isinstance(before, np.ndarray) or not isinstance(after, np.ndarray) or before.shape != after.shape:
        return False
    # Compare the name area even on leaderboards with no scores.
    first = before[274:615, 335:490]
    second = after[274:615, 335:490]
    return bool(first.size and np.mean(np.max(cv2.absdiff(first, second), axis=2) > 24) > 0.012)


def handle_send_friend_life(on_progress=None, *, until_exhausted=False, wait=None):
    wait = time.sleep if wait is None else wait
    popups = StartupUpdates()
    sent = 0
    print("💌 Handling Send Friend Life...")
    deadline = None if until_exhausted else time.monotonic() + LIVES_TIMEOUT
    if until_exhausted:
        print("💌 Scanning Friends from the current position.")
    else:
        top_scroll = 0
        while True:
            screen = device_capture_screen()
            if popups.dismiss_popup(screen, friend_only=True):
                wait(0.5)
                continue
            if detect_templates(screen, FRIEND_TOP_LEADERBOARD_TEMPLATE, FRIEND_TOP_LEADERBOARD_REGION):
                print("✅ Top of Friend Leaderboard reached.")
                break
            if top_scroll >= LIVES_MAX_TOP_SCROLLS or time.monotonic() >= deadline:
                print("⚠️ Friend leaderboard top search limit reached. Skipping heart sending.")
                return False
            print("🔄 Scrolling up to find Send Friend Life...")
            safe_device_scroll(*LEADERBOARD_BOTTOM_POSITION,
                               direction='down', distance=300, duration=150)
            wait(random.uniform(0.8, 1.4))
            top_scroll += 1

    no_button_scroll_count = 0
    down_scroll_count = 0
    stalled = 0
    before_scroll = None
    bottom_seen = False
    while True:
        if deadline is not None and (time.monotonic() >= deadline or down_scroll_count >= LIVES_MAX_DOWN_SCROLLS):
            print("⚠️ Heart sending time/scroll limit reached. Returning to the main loop.")
            break
        screen = device_capture_screen()
        if popups.dismiss_popup(screen, friend_only=True):
            bottom_seen = False
            before_scroll = None
            wait(0.5)
            continue
        if until_exhausted and detect_stage(screen, ['MAINMENU']) != 'MAINMENU':
            print('⚠️ Friends tab was lost while scanning. Heart sending incomplete.')
            return False
        at_bottom = detect_templates(screen, FRIEND_BOTTOM_LEADERBOARD_TEMPLATE, FRIEND_BOTTOM_LEADERBOARD_REGION)
        send_life_button_coords = detect_templates(screen, FRIEND_SEND_LIFE_TEMPLATE, FRIEND_SEND_LIFE_REGION)
        if at_bottom and not send_life_button_coords:
            if bottom_seen or not until_exhausted:
                print("✅ Bottom of Friend Leaderboard verified. No send buttons remain.")
                return True
            bottom_seen = True
            wait(0.5)
            continue
        bottom_seen = False
        if send_life_button_coords:
            no_button_scroll_count = 0
            stalled = 0
            before_scroll = None
            for x, y, w, h in send_life_button_coords:
                if deadline is not None and time.monotonic() >= deadline:
                    print("⚠️ Heart sending time limit reached.")
                    return False
                print("💌 Sending life to friend...")
                safe_device_tap(x + w // 2, y + h // 2)
                wait(random.uniform(0.8, 1.4))
                confirm_position = CONFIRM_SEND_LIFE_BUTTON
                confirm_screen = device_capture_screen()
                if popups.dismiss_popup(confirm_screen, friend_only=True):
                    wait(0.5)
                    break
                if on_progress:
                    matches = detect_templates(confirm_screen, CONFIRM_SEND_LIFE_TEMPLATE, CONFIRM_SEND_LIFE_REGION)
                    if not matches:
                        print('⚠️ Heart confirmation dialog was not recognized.')
                        return False
                    cx, cy, cw, ch = matches[0]
                    confirm_position = (cx + cw // 2, cy + ch // 2)
                print("💌 Confirming send life...")
                safe_device_tap(*confirm_position)
                wait(random.uniform(0.8, 1.4))
                if on_progress:
                    close_x, close_y = CLOSE_SEND_LIFE_DIALOG_BUTTON
                    for _ in range(6):
                        returned = device_capture_screen()
                        if popups.dismiss_popup(returned, friend_only=True):
                            wait(0.5)
                            continue
                        if heart_send_confirmed(screen, returned, (x, y, w, h)):
                            break
                        matches = detect_templates(returned, CONFIRM_SEND_LIFE_TEMPLATE, (480, 380, 950, 540))
                        for cx, cy, cw, ch in matches:
                            if abs(cx + cw // 2 - close_x) <= 32 and abs(cy + ch // 2 - close_y) <= 23:
                                safe_device_tap(cx + cw // 2, cy + ch // 2)
                        wait(0.5)
                    else:
                        print('⚠️ Heart send could not be verified.')
                        return False
                    sent += 1
                    on_progress(sent)
                    print(f'✅ Heart sent. Verified total: {sent}.')
                    screen = returned
                    popups.popup_closes = 0
                else:
                    print("💌 Closing send life dialog...")
                    safe_device_tap(*CLOSE_SEND_LIFE_DIALOG_BUTTON)
                    wait(random.uniform(0.8, 1.4))
        else:
            if until_exhausted:
                if before_scroll is not None:
                    stalled = 0 if heart_list_moved(before_scroll, screen) else stalled + 1
                if stalled >= 3:
                    # Check the end from a different swipe position. A reverse
                    # scroll must reveal earlier rows before a return can prove the end.
                    _, y = FRIEND_LIST_SWIPE_CENTER
                    safe_device_scroll(515, y,
                                       direction='down', distance=145, duration=450)
                    wait(1.2)
                    previous = device_capture_screen()
                    if detect_stage(previous, ['MAINMENU']) != 'MAINMENU':
                        print('⚠️ Friends tab was lost while checking the bottom. Heart sending incomplete.')
                        return False
                    safe_device_scroll(515, y,
                                       direction='up', distance=145, duration=450)
                    wait(1.2)
                    returned = device_capture_screen()
                    if detect_stage(returned, ['MAINMENU']) != 'MAINMENU':
                        print('⚠️ Friends tab was lost while checking the bottom. Heart sending incomplete.')
                        return False
                    buttons = detect_templates(returned, FRIEND_SEND_LIFE_TEMPLATE, FRIEND_SEND_LIFE_REGION)
                    if buttons or heart_list_moved(screen, returned):
                        before_scroll = None
                        stalled = 0
                        continue
                    if heart_list_moved(screen, previous):
                        print('✅ End of Friends list verified by scrolling back and returning. No send buttons remain.')
                        return True
                    print('⚠️ Friends list did not respond to scroll retries. Heart sending incomplete.')
                    return False
                before_scroll = screen
                print("🔄 Scrolling down to find more hearts...")
            else:
                no_button_scroll_count += 1
                if no_button_scroll_count >= LIVES_MAX_EMPTY_SCROLLS:
                    print(f"⚠️ No send life buttons found for {LIVES_MAX_EMPTY_SCROLLS} consecutive checks. Giving up.")
                    break
                print(f"🔄 No send life buttons found, scrolling down... ({no_button_scroll_count}/{LIVES_MAX_EMPTY_SCROLLS})")
            if until_exhausted:
                safe_device_scroll(*FRIEND_LIST_SWIPE_CENTER,
                                   direction='up', distance=115 + 15 * stalled, duration=350)
            else:
                safe_device_scroll(*LEADERBOARD_TOP_POSITION,
                                   direction='up', distance=70, duration=150)
            down_scroll_count += 1
            wait(random.uniform(0.8, 1.4))
    return False


def handle_quick_receive_and_send_lives():
    print("✉️ Handling Quick Receive and Send Lives...")
    time.sleep(random.uniform(0.35, 0.6))
    # Tap the "Mail" button
    safe_device_tap(MAIL_BOX_BUTTON[0], MAIL_BOX_BUTTON[1])
    time.sleep(random.uniform(0.35, 0.6))
    # Tap the "Lives" tab
    safe_device_tap(MAIL_BOX_LIVES_TAB_BUTTON[0], MAIL_BOX_LIVES_TAB_BUTTON[1])
    time.sleep(random.uniform(0.35, 0.6))
    screen = device_capture_screen()
    # No lives to receive
    if detect_templates(screen, NO_LIVES_TO_RECEIVE_TEMPLATE, NO_LIVES_TO_RECEIVE_REGION):
        print("✉️ No lives to receive. Proceeding to send lives...")
        # Close the mail dialog
        safe_device_tap(MAIL_BOX_CLOSE_BUTTON[0], MAIL_BOX_CLOSE_BUTTON[1])
        return
    # Receive all lives
    print("✉️ Receiving all lives...")
    safe_device_tap(QUICK_RECEIVE_AND_SEND_LIVES_BUTTON[0], QUICK_RECEIVE_AND_SEND_LIVES_BUTTON[1])
    time.sleep(random.uniform(0.35, 0.6))
    # Tap all send life buttons
    deadline = time.monotonic() + LIVES_TIMEOUT
    while True:
        if time.monotonic() >= deadline:
            print("⚠️ Quick heart workflow timed out. Closing mailbox.")
            safe_device_tap(MAIL_BOX_CLOSE_BUTTON[0], MAIL_BOX_CLOSE_BUTTON[1])
            return
        # Check if all lifes received and sent!, so break the loop
        screen = device_capture_screen()
        all_lives_received_and_sent = detect_templates(screen, ALL_LIVES_RECEIVED_AND_SENT_TEMPLATE, ALL_LIVES_RECEIVED_AND_SENT_REGION)
        if all_lives_received_and_sent:
            print("✉️ All lives received and sent. Done!")
            # Tap the "Confirm" button
            safe_device_tap(ACCEPT_ALL_LIVES_RECEIVED_AND_SENT_BUTTON[0], ACCEPT_ALL_LIVES_RECEIVED_AND_SENT_BUTTON[1])
            time.sleep(random.uniform(0.35, 0.6))
            # Close the mail dialog
            safe_device_tap(MAIL_BOX_CLOSE_BUTTON[0], MAIL_BOX_CLOSE_BUTTON[1])
            time.sleep(random.uniform(0.35, 0.6))
            break
        # Send lifes to friends
        confirm_send_life_button_coords = detect_templates(screen, CONFIRM_SEND_LIFE_TEMPLATE, CONFIRM_SEND_LIFE_REGION)
        if confirm_send_life_button_coords:
            print("✉️ Sending lives to friends...")
            safe_device_tap(CONFIRM_SEND_LIFE_BUTTON[0], CONFIRM_SEND_LIFE_BUTTON[1])
            time.sleep(random.uniform(0.35, 0.6))
        else:
            time.sleep(0.25)
    print("✉️ Quick Receive and Send Lives completed.")


def close_announcement_dialog():
    print("🖱️ Closing announcement dialog...")
    for i in range(5):
        print(f"🖱️ Tapping close announcement dialog button {i+1}/5")
        safe_device_tap(CLOSE_ANNOUNCEMENT_DIALOG_BUTTON[0], CLOSE_ANNOUNCEMENT_DIALOG_BUTTON[1])
        time.sleep(random.uniform(0.35, 0.6))
    time.sleep(random.uniform(0.35, 0.6))
    device_screen = device_capture_screen()
    if detect_stage(device_screen, ["PARTY_RUN"]) == "PARTY_RUN":
        close_party_run_mode()
    elif detect_stage(device_screen, ["GAME_SETTINGS"]) == "GAME_SETTINGS":
        close_game_settings()


def close_party_run_mode():
    print("🖱️ Closing Party Run mode...")
    safe_device_tap(EXIT_PARTY_RUN_MODE_BUTTON[0], EXIT_PARTY_RUN_MODE_BUTTON[1])
    time.sleep(random.uniform(0.35, 0.6))


def close_game_settings():
    print("🖱️ Closing Game Settings...")
    safe_device_tap(EXIT_GAME_SETTINGS_BUTTON[0], EXIT_GAME_SETTINGS_BUTTON[1])
    time.sleep(random.uniform(0.35, 0.6))
