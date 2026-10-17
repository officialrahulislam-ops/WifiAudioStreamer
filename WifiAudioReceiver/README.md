# Wi-Fi Audio Receiver (Windows)

Receives your Android phone's system audio over local Wi-Fi (Opus over TCP) and plays it
on the Windows default output. Pair it with **WifiAudioSender** (separate Android project).

No cloud, no accounts, no internet. Python + PySide6, ~700 lines.

## Run from source (Windows 10/11, Python 3.11 or 3.12 from python.org)

```bat
cd WifiAudioReceiver
py -3.12 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

## Build `WifiAudioReceiver.exe`

```bat
build.bat
```
(Equivalent to: install requirements, `python assets\make_icon.py`, then PyInstaller with
`--onefile --windowed --collect-all av --collect-all sounddevice --collect-all _sounddevice_data`.)
Result: `dist\WifiAudioReceiver.exe`. The first start of a one-file exe takes a few seconds.
For faster startup replace `--onefile` with `--onedir`.

## Using it

1. Start the app. On first run, allow Windows Firewall (Private networks) or click
   **Add firewall rule** (UAC prompt, limited to your local subnet).
2. Phone and PC on the same Wi-Fi. The window shows a **pairing code** (4 digits, kept between runs).
3. Either enter that code on the phone and tap Connect, **or** click **Connect** next to the phone
   in *Available Devices* (the phone then asks Android for capture consent).
4. Closing the window keeps the app in the tray. Tray menu (right-click the tray icon, it may be under the ^ arrow): Open / Mute / Disconnect / Exit.
   You can also quit with the **Exit app** button in the window or **Ctrl+Q**. The window's X button only hides it to the tray.

## Test the Windows half without a phone

```bat
python tools\test_sender.py 127.0.0.1 <pairing code> 5
```
You should hear a 440 Hz tone. This proves TCP -> Opus decode -> speakers.

## How it works

| Part | Detail |
|---|---|
| Discovery | UDP port 48010: PC beacon every 1 s, phone beacon while its app is open |
| Stream | TCP port 48011, frames `[type u8][len u32][payload]`, payload = one Opus packet (20 ms) |
| Decode | PyAV (FFmpeg Opus decoder) |
| Playback | `sounddevice`, WASAPI shared mode; jitter buffer prebuffers 80 ms and trims to 100 ms above 220 ms |
| Volume / mute | independent app-level booster, 0–300 % (100 % = unchanged, multiplies the Windows volume; soft limiter avoids harsh clipping); system volume is never changed |
| Keep-alive | PC pings every 1 s; 5 s of silence = connection lost, phone reconnects by itself |

The connected screen shows an estimated latency in ms and seconds (buffer + Windows output + ~40 ms assumed for phone capture/encode/Wi-Fi; hover for the breakdown).

Expected end-to-end latency: roughly 150–250 ms (20 ms capture + encode + Wi-Fi + 80 ms buffer + WASAPI).
To lower it, reduce `PREBUFFER_MS` in `player.py` (more risk of crackles on weak Wi-Fi).

## Troubleshooting

* **Phone can't find the PC** – firewall (use *Firewall help*), different Wi-Fi/VLAN, or "AP/client isolation"
  enabled on the router. Use the phone's manual IP field as fallback.
* **Port 48011 in use** – the receiver is already running (look in the tray).
* **No sound** – check the Windows default output device; the app opens it each time a phone connects.
