/*
 * WolfBox - Arduino Desk Light Firmware (WS7)
 *
 * Uses built-in LED only (LED_BUILTIN) for cross-board portability (e.g. Uno, Nano, Mega, Leonardo).
 * Serial communication: 115200 baud.
 *
 * Protocol:
 *   Incoming commands (newline-terminated '\n' or '\r\n'):
 *     STATE running | pass | fail | stuck | offline | idle
 *     FLASH <n>
 *
 *   Responses:
 *     OK <cmd>   (on valid command)
 *     ERR <cmd>  (on unrecognized or malformed command)
 *
 * Patterns (non-blocking, millis()-based):
 *   - running: slow 1 Hz pulse (500ms ON / 500ms OFF)
 *   - pass:    solid ON
 *   - fail:    fast 5 Hz blink (100ms ON / 100ms OFF)
 *   - stuck:   double-blink every 1.5s (100ms ON / 100ms OFF / 100ms ON / 1200ms OFF)
 *   - offline: short blip every 3s (100ms ON / 2900ms OFF)
 *   - idle:    solid OFF
 *   - FLASH n: overlays n quick flashes (120ms ON / 120ms OFF) then returns to current state
 */

#if defined(ARDUINO) || __has_include(<Arduino.h>)
#include <Arduino.h>
#endif

#ifndef LED_BUILTIN
#define LED_BUILTIN 13
#endif

enum LightState {
  STATE_IDLE,
  STATE_RUNNING,
  STATE_PASS,
  STATE_FAIL,
  STATE_STUCK,
  STATE_OFFLINE
};

LightState currentState = STATE_IDLE;

// Flash overlay state
bool inFlashOverlay = false;
int flashCyclesRemaining = 0;
bool flashLedHigh = false;
unsigned long flashPhaseStart = 0;
const unsigned long FLASH_PHASE_MS = 120;

// Serial receive buffer
const size_t RX_BUFFER_SIZE = 64;
char rxBuffer[RX_BUFFER_SIZE];
size_t rxLen = 0;

void setLed(bool on) {
  digitalWrite(LED_BUILTIN, on ? HIGH : LOW);
}

void setup() {
  pinMode(LED_BUILTIN, OUTPUT);
  setLed(false);

  Serial.begin(115200);
  // Optional brief wait for native USB boards (Leonardo, Micro, SAMD)
  unsigned long start = millis();
  while (!Serial && (millis() - start < 1000)) {
    // wait up to 1 second
  }
}

void startFlashOverlay(int count) {
  if (count <= 0) return;
  flashCyclesRemaining = count;
  inFlashOverlay = true;
  flashLedHigh = true;
  flashPhaseStart = millis();
  setLed(true);
}

void updateFlashOverlay(unsigned long now) {
  if (!inFlashOverlay) return;

  if (now - flashPhaseStart >= FLASH_PHASE_MS) {
    flashPhaseStart = now;
    if (flashLedHigh) {
      // Completed ON phase, switch to OFF phase
      flashLedHigh = false;
      setLed(false);
    } else {
      // Completed OFF phase, one full cycle done
      flashCyclesRemaining--;
      if (flashCyclesRemaining <= 0) {
        inFlashOverlay = false;
      } else {
        flashLedHigh = true;
        setLed(true);
      }
    }
  }
}

void updateBasePattern(unsigned long now) {
  switch (currentState) {
    case STATE_IDLE:
      setLed(false);
      break;

    case STATE_PASS:
      setLed(true);
      break;

    case STATE_RUNNING: {
      // 1 Hz cycle: 500ms ON, 500ms OFF
      unsigned long t = now % 1000;
      setLed(t < 500);
      break;
    }

    case STATE_FAIL: {
      // 5 Hz cycle: 200ms period (100ms ON, 100ms OFF)
      unsigned long t = now % 200;
      setLed(t < 100);
      break;
    }

    case STATE_STUCK: {
      // Double-blink every 1.5s (1500ms period)
      // 0..100ms ON, 100..200ms OFF, 200..300ms ON, 300..1500ms OFF
      unsigned long t = now % 1500;
      bool on = (t < 100) || (t >= 200 && t < 300);
      setLed(on);
      break;
    }

    case STATE_OFFLINE: {
      // Short blip every 3s (3000ms period)
      // 0..100ms ON, 100..3000ms OFF
      unsigned long t = now % 3000;
      setLed(t < 100);
      break;
    }
  }
}

void updateLed() {
  unsigned long now = millis();
  if (inFlashOverlay) {
    updateFlashOverlay(now);
  } else {
    updateBasePattern(now);
  }
}

// Strip leading and trailing whitespace in-place
char* trimWhitespace(char* str) {
  while (*str == ' ' || *str == '\t' || *str == '\r' || *str == '\n') {
    str++;
  }
  if (*str == '\0') {
    return str;
  }
  char* end = str + strlen(str) - 1;
  while (end > str && (*end == ' ' || *end == '\t' || *end == '\r' || *end == '\n')) {
    *end = '\0';
    end--;
  }
  return str;
}

void handleCommand(char* raw) {
  char* cmd = trimWhitespace(raw);
  if (cmd[0] == '\0') {
    return; // empty line
  }

  // Handle "STATE <name>"
  if (strncmp(cmd, "STATE", 5) == 0 && (cmd[5] == ' ' || cmd[5] == '\0')) {
    char* arg = trimWhitespace(cmd + 5);
    if (strcmp(arg, "running") == 0) {
      currentState = STATE_RUNNING;
      Serial.print("OK ");
      Serial.println(cmd);
      return;
    } else if (strcmp(arg, "pass") == 0) {
      currentState = STATE_PASS;
      Serial.print("OK ");
      Serial.println(cmd);
      return;
    } else if (strcmp(arg, "fail") == 0) {
      currentState = STATE_FAIL;
      Serial.print("OK ");
      Serial.println(cmd);
      return;
    } else if (strcmp(arg, "stuck") == 0) {
      currentState = STATE_STUCK;
      Serial.print("OK ");
      Serial.println(cmd);
      return;
    } else if (strcmp(arg, "offline") == 0) {
      currentState = STATE_OFFLINE;
      Serial.print("OK ");
      Serial.println(cmd);
      return;
    } else if (strcmp(arg, "idle") == 0) {
      currentState = STATE_IDLE;
      Serial.print("OK ");
      Serial.println(cmd);
      return;
    } else {
      Serial.print("ERR ");
      Serial.println(cmd);
      return;
    }
  }

  // Handle "FLASH <n>"
  if (strncmp(cmd, "FLASH", 5) == 0 && (cmd[5] == ' ' || cmd[5] == '\0')) {
    char* arg = trimWhitespace(cmd + 5);
    int count = atoi(arg);
    if (count > 0) {
      startFlashOverlay(count);
      Serial.print("OK ");
      Serial.println(cmd);
      return;
    } else {
      Serial.print("ERR ");
      Serial.println(cmd);
      return;
    }
  }

  // Unknown command
  Serial.print("ERR ");
  Serial.println(cmd);
}

void loop() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\r') {
      continue; // discard carriage return
    }
    if (c == '\n') {
      rxBuffer[rxLen] = '\0';
      if (rxLen > 0) {
        handleCommand(rxBuffer);
      }
      rxLen = 0;
    } else {
      if (rxLen < RX_BUFFER_SIZE - 1) {
        rxBuffer[rxLen++] = c;
      } else {
        // Buffer overflow: drop and reset buffer
        rxLen = 0;
      }
    }
  }

  updateLed();
}
