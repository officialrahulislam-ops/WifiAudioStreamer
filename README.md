# Wi-Fi Audio Streamer

Stream your Android phone's audio to your Windows PC over your local Wi-Fi.
No internet, no accounts, no cloud: audio goes straight from the phone to the PC.

## Downloads
- **WifiAudioReceiver.exe**: for Windows 10/11
- **WifiAudioSender.apk**: for Android 10 or newer

## How to use
1. Put your phone and PC on the same Wi-Fi network.
2. Run **WifiAudioReceiver.exe** on the PC. If Windows Firewall asks, allow it on Private networks.
3. Install **WifiAudioSender.apk** on the phone and open it. Your PC should appear under "Receiver".
   If it doesn't, tap "Can't find your PC?" and type the PC's IP address.
4. Enter the 4-digit **pairing code** shown in the PC app and tap **Connect**.
   (Or click **Connect** next to your phone in the PC app.)
5. Accept the permission prompts on the phone, then play something. It will come out of your PC.

Closing the PC window keeps it running in the system tray. Use the **Exit app** button
(or Ctrl+Q, or the tray menu) to quit fully.

## How it works
- **Capture:** the Android app uses Android's built-in system audio capture
  (AudioPlaybackCapture), so it records what the phone is *playing*, not what the microphone hears.
- **Compression:** the audio is encoded with the Opus codec (48 kHz stereo, 128 kbps, 20 ms frames),
  which keeps bandwidth low and latency small.
- **Sending:** the packets go over a direct TCP connection on your local network.
  A foreground service keeps it running with the screen off or other apps open.
- **Finding each other:** both apps broadcast small UDP messages on the local network,
  so the PC and phone find each other automatically. A 4-digit pairing code stops
  other devices from connecting by accident.
- **Playback:** the PC app decodes the audio and plays it through the Windows default
  output, using a small buffer to smooth out Wi-Fi hiccups.
- **Volume booster:** the PC app has its own volume control from 0 to 300%, separate from
  the Windows volume. 100% leaves the sound unchanged, and anything above boosts it on top
  of Windows' own level.
- **Latency:** the PC app shows an estimated delay in milliseconds and seconds.
  It's an estimate, not an exact measurement.
- **Reconnecting:** if Wi-Fi drops, the phone keeps trying to reconnect automatically.

## Good to know
- While streaming, the phone's media volume is set to 0 and restored afterwards, so you
  hear the audio on the PC instead. You can turn this off in the app.
- Some apps block audio capture (Android's rule), and they will play silence.
- Windows may show a SmartScreen warning because the .exe isn't code-signed:
  click **More info → Run anyway**.
- Android will ask you to allow installing from unknown sources, because the APK
  isn't from the Play Store.

## Credits
This project was made entirely by **Claude** (an AI assistant made by Anthropic).
The idea came from me, for my own personal use. I take no credit for writing the code:
Claude did all of it. I'm sharing it in case it's useful to others.

Provided as-is, with no warranty.
