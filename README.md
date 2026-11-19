# cookierun-classic-autorun

[English](#english) · [ภาษาไทย](#ภาษาไทย)

## English

A Windows desktop interface for running CookieRun Classic in LDPlayer and tracking Mystery Box results. This is a community project based on [max180643/cookierun-classic-bot](https://github.com/max180643/cookierun-classic-bot).

### Set up and open the app

[Step-by-step Windows setup with screenshots (Thai)](docs/SETUP-TH.md)

1. Install [Python 3.13 for Windows](https://www.python.org/downloads/windows/) with Tcl/Tk and the `py` launcher. Install [Android SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools), add the extracted `platform-tools` folder to Windows PATH, and open a new terminal to verify `adb version`.
2. In LDPlayer, set the Android resolution to **1280 × 720** and enable **ADB debugging → Local connection**. Save and restart LDPlayer. The default connection is `127.0.0.1:5555`. If your port differs, change `DEVICE_PORT` in `config.py`.
3. Double-click **cookierun-classic-autorun.cmd**. On first launch, it creates `.venv` and installs the dependencies. Leave the setup window open until the app appears.
4. Open the game to its main menu and review **Saved Settings** before clicking **Start**. Click **Stop** and wait for **Session Summary** when you finish.

If automatic setup fails, open PowerShell in the project folder and run:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
adb version
```

Double-click **cookierun-classic-autorun.cmd** again after the commands succeed.

### Settings and timing

- **Fast Start**, **Cookie Relay**, and **Random Boost** can buy and use in-game boosts. Select **Off** for Random Boost to skip that purchase.
- **Jump 7 times at start** waits for the controls. With Fast Start on, jumps are skipped if the app cannot confirm that normal controls have returned.
- **Claim Relics** handles the Relic reward screen when detected.
- **Stop after N rounds** stops at the main menu after that many completed rounds. The header shows progress such as `7 / 20 rounds completed`. Enter `0` for unlimited runs. The app saves the settings when you start.
- The status is green when connected, amber while connecting, waiting, or stopping, and red for errors.
- After the first round, the app adds a fixed wait between runs. At the main menu, it checks **Mailbox → Lives** about once an hour and attempts quick receive and send if hearts are available.
- The desktop UI has no scheduled game restart. If it detects player verification or loses the game connection, it stops and shows the reason.

### Review or clean up history

- **Latest Round** displays the latest box counts. Hover over a box for its name.
- **Session Summary** shows Total Rounds, Total Boxes, and Total Time, with box counts by type. Unread results appear as unknown.
- **Session History** lets you choose a finished session by date and open its associated log when available.
- **Open Session Folder** opens `stats/sessions/` in File Explorer. With the app stopped, move unwanted old JSON files out of the folder or delete them yourself. Close and reopen **Session History** to refresh it. Saved logs are separate in `stats/logs/`.
- **Open Logs** shows saved activity by date. Use **Errors & warnings** to filter the list, or **Copy Log** to copy the text. The app uses colored text labels such as **[WAIT]** and **[ERROR]**. Saved log files keep the original messages. **? Help** opens the in-app guide.

### Local files

Git ignores `.venv/`, `last_settings.json`, `stats/`, caches, and backups. Keep the settings and stats folders when moving an existing installation.

## ภาษาไทย

โปรแกรมบน Windows สำหรับเล่น CookieRun Classic ผ่าน LDPlayer และสรุปจำนวน Mystery Box พัฒนาต่อจาก [โปรเจกต์ของ max180643](https://github.com/max180643/cookierun-classic-bot)

### ตั้งค่าและเปิดโปรแกรม

[คู่มือติดตั้งบน Windows แบบละเอียดพร้อมภาพหน้าจอ](docs/SETUP-TH.md)

1. ติดตั้ง [Python 3.13 สำหรับ Windows](https://www.python.org/downloads/windows/) พร้อม Tcl/Tk และตัวเรียก `py` จากนั้นติดตั้ง [Android SDK Platform-Tools](https://developer.android.com/tools/releases/platform-tools) เพิ่มโฟลเดอร์ `platform-tools` ที่แตกไฟล์แล้วลงใน Windows PATH แล้วเปิดเทอร์มินัลใหม่เพื่อเช็กด้วย `adb version`
2. ใน LDPlayer ตั้งความละเอียด Android เป็น **1280 × 720** แล้วเปิด **ADB debugging → Local connection** จากนั้นบันทึกและเปิด LDPlayer ใหม่ ค่าเริ่มต้นคือ `127.0.0.1:5555` ถ้าพอร์ตเครื่องคุณต่างจากนี้ ให้แก้ `DEVICE_PORT` ใน `config.py`
3. ดับเบิลคลิก **cookierun-classic-autorun.cmd** ตอนเปิดครั้งแรก โปรแกรมจะสร้าง `.venv` และติดตั้งไลบรารีให้ รอจนหน้าต่างโปรแกรมเปิดขึ้น
4. เปิดเกมให้ถึงเมนูหลัก ตรวจ **Saved Settings** แล้วกด **Start** เมื่อต้องการหยุดให้กด **Stop** และรอดู **Session Summary**

ถ้าติดตั้งอัตโนมัติไม่สำเร็จ ให้เปิด PowerShell ในโฟลเดอร์โปรเจกต์แล้วรันคำสั่งนี้

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
adb version
```

เมื่อทุกคำสั่งผ่าน ให้ดับเบิลคลิก **cookierun-classic-autorun.cmd** อีกครั้ง

### ค่าตั้งและเวลาทำงาน

- **Fast Start**, **Cookie Relay** และ **Random Boost** สามารถซื้อและใช้บูสต์ในเกมได้ เลือก **Off** ใน Random Boost เพื่อข้ามการซื้อนั้น
- **Jump 7 times at start** รอจนปุ่มควบคุมพร้อม ถ้าเปิด Fast Start แล้วตรวจไม่พบว่าปุ่มควบคุมกลับมา โปรแกรมจะข้ามการกระโดด
- **Claim Relics** รับรางวัล Relic เมื่อพบหน้ารับรางวัล
- **Stop after N rounds** หยุดที่เมนูหลักเมื่อจบครบตามจำนวน แถบด้านบนแสดงจำนวนรอบที่ทำเสร็จ เช่น `7 / 20 rounds completed` ใส่ `0` ถ้าไม่จำกัดรอบ โปรแกรมจำค่าที่เลือกไว้เมื่อกด Start
- สถานะเป็นสีเขียวเมื่อเชื่อมต่อ สีเหลืองอำพันระหว่างเชื่อมต่อ รอ หรือกำลังหยุด และสีแดงเมื่อมีข้อผิดพลาด
- หลังรอบแรกจะมีเวลารอคงที่ก่อนเริ่มรอบถัดไป เมื่ออยู่เมนูหลัก โปรแกรมจะตรวจ **Mailbox → Lives** ประมาณทุกชั่วโมงและลองรับส่งแบบด่วนเมื่อมีหัวใจ
- UI ไม่มีการตั้งเวลารีสตาร์ตเกม ถ้าตรวจพบหน้าตรวจสอบผู้เล่นหรือการเชื่อมต่อเกมหลุด โปรแกรมจะหยุดและแจ้งเหตุผล

### ดูและจัดการข้อมูลย้อนหลัง

- **Latest Round** แสดงจำนวนกล่องรอบล่าสุด ชี้ที่รูปกล่องเพื่อดูชื่อ
- **Session Summary** แสดง Total Rounds, Total Boxes และ Total Time พร้อมยอดกล่องแยกประเภท ผลที่อ่านไม่ได้จะแสดงว่าไม่ทราบ
- **Session History** เลือกดูสรุปตามวันเวลา และเปิด Log ของรอบการใช้งานนั้นได้ถ้ามี
- **Open Session Folder** เปิด `stats/sessions/` ใน File Explorer หยุดโปรแกรมก่อนย้ายหรือลบไฟล์ JSON เก่าที่ไม่ใช้ แล้วปิดและเปิด **Session History** ใหม่เพื่อให้รายการอัปเดต ส่วนไฟล์ Log อยู่แยกใน `stats/logs/`
- **Open Logs** เลือกดูข้อความย้อนหลังตามวันเวลา ใช้ **Errors & warnings** เพื่อกรอง หรือ **Copy Log** เพื่อคัดลอกข้อความ ในแอปใช้ป้ายสี เช่น **[WAIT]** และ **[ERROR]** ส่วนไฟล์ Log เก็บข้อความต้นฉบับ กด **? Help** เพื่อเปิดคู่มือในโปรแกรม

### ไฟล์ในเครื่อง

Git จะข้าม `.venv/`, `last_settings.json`, `stats/` รวมถึงแคชและไฟล์สำรอง หากย้ายโปรแกรมไปเครื่องอื่น ให้เก็บ `last_settings.json` และ `stats/` ไว้เพื่อใช้ค่าตั้งและประวัติเดิม
