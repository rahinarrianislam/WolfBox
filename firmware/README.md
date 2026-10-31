# WolfBox Arduino Desk Light (WS7)

The Arduino Desk Light uses the board's built-in LED (`LED_BUILTIN`) to provide real-time ambient status feedback for WolfBox without needing any external circuits, breadboards, or extra components.

---

## 1. LED Patterns & App State Mapping

| Command / State | Visual Pattern | App Event / Meaning |
|---|---|---|
| `STATE running` | Slow 1 Hz pulse (500ms ON / 500ms OFF) | Running pytest suite in background |
| `STATE pass` | Solid ON | All tests passed |
| `STATE fail` | Fast 5 Hz blink (100ms ON / 100ms OFF) | Test suite failures detected |
| `STATE stuck` | Double-blink every 1.5s (100ms ON, 100ms OFF, 100ms ON, 1200ms OFF) | Student is stuck (nudge banner active) |
| `STATE offline` | Short blip every 3s (100ms ON, 2900ms OFF) | Gemma LLM backend running locally (offline) |
| `STATE idle` | Solid OFF | Default initial state / idle |
| `FLASH <n>` | Temporary overlay of *n* quick flashes (120ms ON / 120ms OFF), then resumes previous state | `FLASH 3` on newly synced course document |

---

## 2. Compiling and Flashing with `arduino-cli`

### Step 1: Install core (AVR for Uno, Nano, Mega, etc.)
```bash
arduino-cli core install arduino:avr
```

### Step 2: Compile firmware
For an Arduino Uno:
```bash
arduino-cli compile --fqbn arduino:avr:uno firmware/desk_light
```
*(Or specify other FQBNs, such as `arduino:avr:nano` or `arduino:avr:mega`)*.

### Step 3: Identify board port and upload
List connected boards to find the serial port:
```bash
arduino-cli board list
```
Upload the sketch to the identified port (e.g. `/dev/cu.usbmodem1101` on macOS or `COM3` on Windows):
```bash
arduino-cli upload -p <port> --fqbn arduino:avr:uno firmware/desk_light
```

---

## 3. Testing with a Serial Monitor

The firmware communicates over USB Serial at **115200 baud** with newline-terminated (`\n` or `\r\n`) ASCII strings.

### Using `arduino-cli monitor`
```bash
arduino-cli monitor -p <port> -c baudrate=115200
```

### Interactive Test Commands
Send the following commands to verify:
```text
STATE running
-> Responds: OK STATE running   (LED pulses slowly at 1 Hz)

STATE pass
-> Responds: OK STATE pass      (LED turns solid ON)

STATE fail
-> Responds: OK STATE fail      (LED blinks rapidly at 5 Hz)

STATE stuck
-> Responds: OK STATE stuck     (LED double-blinks every 1.5s)

STATE offline
-> Responds: OK STATE offline   (LED blips every 3s)

FLASH 3
-> Responds: OK FLASH 3         (LED blinks 3 times quickly, then returns to previous state)

STATE idle
-> Responds: OK STATE idle      (LED turns OFF)

UNKNOWN_CMD
-> Responds: ERR UNKNOWN_CMD    (Error reply on unrecognized input)
```

---

## 4. Web Serial Frontend Integration (`serial.js`)

WolfBox includes a browser-side Web Serial driver in [`orchestrator/static/serial.js`](../orchestrator/static/serial.js):

> [!NOTE]
> **Browser Support:** Web Serial (`navigator.serial`) is supported in **Google Chrome**, **Microsoft Edge**, and other Chromium-based browsers on desktop. It is not supported in Safari or Firefox. It requires a secure context (`https://` or `http://localhost`).

### JavaScript API
The driver attaches to `window` and exposes both direct functions and the `window.DeskLight` namespace:

```javascript
// Check browser support
if (DeskLight.supported()) {
  // Show "Connect desk light" button in UI
}

// Connect from a click handler (must be triggered by a user gesture):
connectButton.addEventListener('click', async () => {
  const success = await DeskLight.connect();
  if (success) {
    console.log("Connected to desk light!");
  }
});

// Update state based on WolfBox events:
DeskLight.setState('running');  // when tests start
DeskLight.setState('pass');     // on test pass
DeskLight.setState('fail');     // on test fail
DeskLight.setState('stuck');    // when nudge is active
DeskLight.setState('offline');  // when LLM is local/offline
DeskLight.setState('idle');     // reset/standby

// Overlay flash on doc sync:
DeskLight.flash(3);             // 3 quick flashes on new synced doc

// Check connection status:
DeskLight.isConnected();        // returns true/false
```

All functions are safe no-ops if the board is disconnected or if the browser lacks Web Serial support. They never throw exceptions to caller code.
