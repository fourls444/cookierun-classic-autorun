# cookierun-classic-autorun

[English](#english) · [ภาษาไทย](#ภาษาไทย)

## English

A Windows desktop interface for running CookieRun Classic in LDPlayer and tracking Mystery Box results. This is a community project based on [max180643/cookierun-classic-bot](https://github.com/max180643/cookierun-classic-bot).

### Set up and open the app

[Step-by-step Windows setup with screenshots (Thai)](docs/SETUP-TH.md)

1. Install [Python 3.13 for Windows](https://www.python.org/downloads/windows/) with Tcl/Tk and the `py` launcher. Install [Android SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools), add the extracted `platform-tools` folder to Windows PATH, and open a new terminal to verify `adb version`.
2. In LDPlayer, set the Android resolution to **1280 × 720** and enable **ADB debugging → Local connection**. Save and restart LDPlayer. The default connection is `127.0.0.1:5555`. If your port differs, change `DEVICE_PORT` in `config.py`.
3. Double-click **cookierun-classic-autorun.cmd**. On first launch, it creates `.venv` and installs the dependencies. Leave the setup window open until the app appears.
4. Open the game to its main menu and review **Settings** before clicking **Start**. Click **Stop** and wait for **Summary** when you finish.

If automatic setup fails, open PowerShell in the project folder and run:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
adb version
```

Double-click **cookierun-classic-autorun.cmd** again after the commands succeed.

### Settings and timing

- Open **Send Hearts** or **Open Gifts** in the top bar for a separate window with its own **Start** and **Stop**. Both return to the main menu when finished. Set **Gift Draw Limit** in **Open Gifts** before starting.
- **Fast Start**, **Cookie Relay**, and **Random Boost** can buy and use in-game boosts. Select **Off** for Random Boost to skip that purchase.
- **Jump 7 times at start** waits for the controls. With Fast Start on, jumps are skipped if the app cannot confirm that normal controls have returned.
- **Claim Relics** handles the Relic reward screen when detected.
- **Round Limit** stops at the main menu after that many completed rounds. The header shows progress such as `7 / 20 rounds completed`. Enter `0` for unlimited runs. The app saves the settings when you start.
- The status is green when connected, amber while connecting, waiting, or stopping, and red for errors.
- After the first round, the app adds a fixed wait between runs. At the main menu, it checks **Mailbox → Lives** about once an hour and attempts quick receive and send if hearts are available.
- The app closes recognized event and promotional popups using their **X** before starting a round. It checks the next screen after each close and stops after six taps if the popups persist.
- On **Connection Lost**, the app taps **Confirm** and waits for the main menu. It retries once if the dialog is still visible, then stops with a message if the main menu does not return. It stops when player verification appears.

### Review or clean up history

- **Latest Round** shows Coins, EXP, and box counts from the latest result. Hover over a box for its name.
- **Summary** totals only completed rounds and adds their durations, rewards, and boxes by type. Coins and EXP are sampled after the result screen settles. Partial totals show how many rounds were read.
- **History** shows the summary for a finished session selected by date. The box distribution lists counts that occurred and uses only rounds with a confirmed box count.
- **Rounds**, next to **Open Logs**, lets you choose a saved run and view Coins, EXP and boxes for each completed round. Select a round to see its box types and open its saved screenshot when available. A dash marks an unread value.
- **Open Folder** opens `stats/sessions/` in File Explorer. With the app stopped, move unwanted old JSON files out of the folder or delete them yourself. Close and reopen **History** to refresh it. Saved logs are separate in `stats/logs/`.
- **Open Logs** shows saved activity by date. Use **Error & Warnings** to filter the list, or **Copy Log** to copy the text. The app uses colored text labels such as **[WAIT]** and **[ERROR]**. Saved log files keep the original messages. The **?** button opens the in-app guide.

### Local files

Git ignores `.venv/`, `last_settings.json`, `stats/`, caches, and backups. Keep the settings and stats folders when moving an existing installation.

## ภาษาไทย

โปรแกรมบน Windows สำหรับเล่น CookieRun Classic ผ่าน LDPlayer และสรุปจำนวน Mystery Box พัฒนาต่อจาก [โปรเจกต์ของ max180643](https://github.com/max180643/cookierun-classic-bot)

### ตั้งค่าและเปิดโปรแกรม

[คู่มือติดตั้งบน Windows แบบละเอียดพร้อมภาพหน้าจอ](docs/SETUP-TH.md)

1. ติดตั้ง [Python 3.13 สำหรับ Windows](https://www.python.org/downloads/windows/) พร้อม Tcl/Tk และตัวเรียก `py` จากนั้นติดตั้ง [Android SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools) เพิ่มโฟลเดอร์ `platform-tools` ที่แตกไฟล์แล้วลงใน Windows PATH แล้วเปิดเทอร์มินัลใหม่เพื่อเช็กด้วย `adb version`
2. ใน LDPlayer ตั้งความละเอียด Android เป็น **1280 × 720** แล้วเปิด **ADB debugging → Local connection** จากนั้นบันทึกและเปิด LDPlayer ใหม่ ค่าเริ่มต้นคือ `127.0.0.1:5555` ถ้าพอร์ตเครื่องคุณต่างจากนี้ ให้แก้ `DEVICE_PORT` ใน `config.py`
3. ดับเบิลคลิก **cookierun-classic-autorun.cmd** ตอนเปิดครั้งแรก โปรแกรมจะสร้าง `.venv` และติดตั้งไลบรารีให้ รอจนหน้าต่างโปรแกรมเปิดขึ้น
4. เปิดเกมให้ถึงเมนูหลัก ตรวจ **Settings** แล้วกด **Start** เมื่อต้องการหยุดให้กด **Stop** และรอดู **Summary**

ถ้าติดตั้งอัตโนมัติไม่สำเร็จ ให้เปิด PowerShell ในโฟลเดอร์โปรเจกต์แล้วรันคำสั่งนี้

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
adb version
```

เมื่อทุกคำสั่งผ่าน ให้ดับเบิลคลิก **cookierun-classic-autorun.cmd** อีกครั้ง

### ค่าตั้งและเวลาทำงาน

- กด **Send Hearts** หรือ **Open Gifts** ในแถบด้านบน เพื่อเปิดหน้าต่างแยกที่มีปุ่ม **Start / Stop** ของตัวเอง เมื่อทำงานเสร็จแอปจะกลับเมนูหลัก ตั้งจำนวนครั้งที่ **Gift Draw Limit** ในหน้าต่าง **Open Gifts** ก่อนเริ่ม
- **Fast Start**, **Cookie Relay** และ **Random Boost** สามารถซื้อและใช้บูสต์ในเกมได้ เลือก **Off** ใน Random Boost เพื่อข้ามการซื้อนั้น
- **Jump 7 times at start** รอจนปุ่มควบคุมพร้อม ถ้าเปิด Fast Start แล้วตรวจไม่พบว่าปุ่มควบคุมกลับมา โปรแกรมจะข้ามการกระโดด
- **Claim Relics** รับรางวัล Relic เมื่อพบหน้ารับรางวัล
- **Round Limit** หยุดที่เมนูหลักเมื่อจบครบตามจำนวน แถบด้านบนแสดงจำนวนรอบที่ทำเสร็จ เช่น `7 / 20 rounds completed` ใส่ `0` ถ้าไม่จำกัดรอบ โปรแกรมจำค่าที่เลือกไว้เมื่อกด Start
- สถานะเป็นสีเขียวเมื่อเชื่อมต่อ สีเหลืองอำพันระหว่างเชื่อมต่อ รอ หรือกำลังหยุด และสีแดงเมื่อมีข้อผิดพลาด
- หลังรอบแรกจะมีเวลารอคงที่ก่อนเริ่มรอบถัดไป เมื่ออยู่เมนูหลัก โปรแกรมจะตรวจ **Mailbox → Lives** ประมาณทุกชั่วโมงและลองรับส่งแบบด่วนเมื่อมีหัวใจ
- ก่อนเริ่มรอบ แอปจะปิดหน้ากิจกรรมและโปรโมชันที่ตรวจพบปุ่ม **X** แล้วตรวจหน้าถัดไปทีละใบ หากกดครบ 6 ครั้งแล้วยังพบหน้าต่าง แอปจะหยุดและแจ้งเหตุผล
- เมื่อขึ้น **Connection Lost** แอปจะกด **Confirm** แล้วรอเมนูหลัก ถ้าหน้าต่างยังอยู่จะลองอีกครั้ง หากกลับเข้าเมนูไม่ได้หรือพบหน้าตรวจสอบผู้เล่น แอปจะหยุดและแจ้งเหตุผล

### ดูและจัดการข้อมูลย้อนหลัง

- **Latest Round** แสดง Coins, EXP และจำนวนกล่องรอบล่าสุด ชี้ที่รูปกล่องเพื่อดูชื่อ
- **Summary** รวมเวลา ยอด Coins และ EXP และกล่องจากรอบที่จบแล้วเท่านั้น โปรแกรมรอหน้าผลการแข่งขันนิ่งก่อนอ่านยอด ถ้าอ่านได้ไม่ครบทุกรอบ จะแสดงจำนวนรอบที่อ่านได้กำกับยอดรวม
- **History** ใช้เลือกดูสรุปรอบการใช้งานย้อนหลังตามวันเวลา ตารางจำนวนกล่องแสดงเฉพาะจำนวนที่พบและคิดเปอร์เซ็นต์จากรอบที่อ่านจำนวนกล่องได้
- **Rounds** อยู่ข้าง **Open Logs** ใช้เลือกวันเวลาและดู Coins, EXP และกล่องทีละรอบ เลือกรอบเพื่อดูประเภทกล่องและเปิดภาพที่บันทึกไว้ถ้ามี ขีดหมายถึงอ่านค่าไม่ได้
- **Open Folder** เปิด `stats/sessions/` ใน File Explorer หยุดโปรแกรมก่อนย้ายหรือลบไฟล์ JSON เก่าที่ไม่ใช้ แล้วปิดและเปิด **History** ใหม่เพื่อให้รายการอัปเดต ส่วนไฟล์ Log อยู่แยกใน `stats/logs/`
- **Open Logs** เลือกดูข้อความย้อนหลังตามวันเวลา ใช้ **Error & Warnings** เพื่อกรอง หรือ **Copy Log** เพื่อคัดลอกข้อความ ในแอปใช้ป้ายสี เช่น **[WAIT]** และ **[ERROR]** ส่วนไฟล์ Log เก็บข้อความต้นฉบับ กด **?** เพื่อเปิดคู่มือในโปรแกรม

### ไฟล์ในเครื่อง

Git จะข้าม `.venv/`, `last_settings.json`, `stats/` รวมถึงแคชและไฟล์สำรอง หากย้ายโปรแกรมไปเครื่องอื่น ให้เก็บ `last_settings.json` และ `stats/` ไว้เพื่อใช้ค่าตั้งและประวัติเดิม
