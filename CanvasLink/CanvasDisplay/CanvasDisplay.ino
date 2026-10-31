// UNO Q demonstration: happy message first, then sad message and clock.
#include <Arduino_RouterBridge.h>
#include <ArduinoGraphics.h>
#include <Arduino_LED_Matrix.h>

Arduino_LED_Matrix matrix;
const unsigned long SCROLL_STEP_MS = 85;
const uint8_t HAPPY[7] = {0b0111110, 0b1000001, 0b1010101, 0b1000001, 0b1010101, 0b1001001, 0b0111110};
const uint8_t SAD[7] = {0b0111110, 0b1000001, 0b1010101, 0b1000001, 0b1001001, 0b1010101, 0b0111110};
const uint8_t CLOCK_RIM[7] = {0b0111110, 0b1000001, 0b1000001, 0b1000001, 0b1000001, 0b1000001, 0b0111110};

bool liveMode = false;
unsigned long lastContact = 0;
unsigned long lastUpdate = 0;
unsigned long generation = 0;
String incoming;
String currentMessage;
char currentMood = 'I';

void receiveUpdate();
void pumpWait(unsigned long duration) {
  const unsigned long started = millis();
  const unsigned long version = generation;
  while (millis() - started < duration && generation == version) {
    receiveUpdate();
    delay(5);
  }
}

void drawIcons(int left, bool happy) {
  matrix.beginDraw();
  matrix.background(0, 0, 0);
  matrix.ArduinoGraphics::clear();  // Clear the canvas before drawing each frame.
  matrix.stroke(127, 0, 0);
  const int width = 7;
  for (int y = 0; y < 7; y++) {
    for (int x = 0; x < width; x++) {
      if ((happy ? HAPPY[y] : SAD[y]) & (1 << (width - 1 - x))) {
        matrix.point(left + x, y);
      }
    }
  }
  matrix.endDraw();
}

// Eight hand positions, advancing clockwise. Hands rotate for five seconds.
void animateClock() {
  const int8_t handX[8] = {0, 2, 2, 2, 0, -2, -2, -2};
  const int8_t handY[8] = {-2, -2, 0, 2, 2, 2, 0, -2};
  const unsigned long started = millis();
  const unsigned long version = generation;
  for (int frame = 0; frame < 40 && generation == version; frame++) {
    matrix.beginDraw();
    matrix.background(0, 0, 0);
    matrix.ArduinoGraphics::clear();
    matrix.stroke(127, 0, 0);
    for (int y = 0; y < 7; y++) {
      for (int x = 0; x < 7; x++) {
        if (CLOCK_RIM[y] & (1 << (6 - x))) {
          matrix.point(3 + x, y);
        }
      }
    }
    // Short hour hand and rotating minute hand.
    matrix.line(6, 3, 7, 3);
    matrix.line(6, 3, 6 + handX[frame % 8], 3 + handY[frame % 8]);
    matrix.endDraw();
    const unsigned long deadline = (unsigned long)(frame + 1) * 5000UL / 40;
    while (millis() - started < deadline && generation == version) {
      receiveUpdate();
      delay(1);
    }
  }
  matrix.clear();
}

// Party popper: a cone at the lower left launches confetti upward and right.
void animateConfetti() {
  const unsigned long version = generation;
  const unsigned long started = millis();
  const int8_t burstX[8] = {3, 4, 5, 5, 6, 7, 8, 9};
  const int8_t burstY[8] = {1, -1, 0, 2, -2, 1, -1, 3};
  for (int frame = 0; frame < 30 && generation == version; frame++) {
    const int phase = frame % 10;
    matrix.beginDraw();
    matrix.background(0, 0, 0);
    matrix.ArduinoGraphics::clear();
    matrix.stroke(127, 0, 0);

    // Striped triangular cone, pointing toward its opening at (4, 4).
    matrix.line(0, 7, 2, 3);
    matrix.line(0, 7, 5, 6);
    matrix.line(2, 3, 5, 6);
    matrix.line(1, 6, 3, 6);
    matrix.point(2, 5);

    if (phase == 1 || phase == 2) {
      // Small spark at the opening before the confetti expands.
      matrix.line(5, 3, 7, 1);
      matrix.point(4, 1);
      matrix.point(7, 4);
    }
    if (phase >= 2 && phase <= 8) {
      const int age = phase - 2;
      for (int i = 0; i < 8; i++) {
        const int x = 4 + burstX[i] * age / 6;
        const int y = 4 - (6 - burstY[i]) * age / 6 + age * age / 18;
        if (x >= 0 && x < 13 && y >= 0 && y < 8) {
          matrix.point(x, y);
        }
      }
    }
    matrix.endDraw();
    while (millis() - started < (unsigned long)(frame + 1) * 100UL && generation == version) {
      receiveUpdate();
      delay(1);
    }
  }
  matrix.clear();
}

// Scroll without blocking USB polling, including during long assignment names.
bool scrollMessage(String message) {
  const unsigned long version = generation;
  const int length = message.length() * matrix.textFontWidth();
  for (int left = 13; left >= -length; left--) {
    receiveUpdate();
    if (generation != version) return false;
    matrix.beginDraw();
    matrix.background(0, 0, 0);
    matrix.ArduinoGraphics::clear();
    matrix.stroke(127, 0, 0);
    matrix.text(message, left, 0);
    matrix.endDraw();
    pumpWait(SCROLL_STEP_MS);
  }
  return generation == version;
}

void showMessage(String message, bool happy) {
  const unsigned long version = generation;
  if (!scrollMessage(message)) return;
  for (int left = 13; left >= 3; left--) {
    if (generation != version) return;
    drawIcons(left, happy);
    pumpWait(SCROLL_STEP_MS);
  }
  pumpWait(2000);
  for (int left = 2; left >= -7; left--) {
    if (generation != version) return;
    drawIcons(left, happy);
    pumpWait(SCROLL_STEP_MS);
  }
  if (generation != version) return;
  if (happy) animateConfetti();
  else animateClock();
  pumpWait(1000);
}

void enterDemo() {
  if (liveMode) {
    liveMode = false;
    generation++;
  }
}

// Updates carry no API token. K = heartbeat, D = return to demonstration.
void receiveUpdate() {
  while (Serial.available()) {
    const char c = Serial.read();
    if (c == '\n') {
      if (incoming == "K") {
        lastContact = millis();
        Serial.println("CANVAS_OK");
      } else if (incoming == "D") {
        enterDemo();
        Serial.println("CANVAS_OK");
      } else if (incoming == "Q") {
        Serial.println(liveMode ? "MODE_LIVE" : "MODE_DEMO");
        Serial.println("CANVAS_OK");
      } else if (incoming.length() >= 3 && incoming[1] == '\t' &&
          (incoming[0] == 'H' || incoming[0] == 'S' || incoming[0] == 'I')) {
        const String next = "   " + incoming.substring(2) + "   ";
        if (!liveMode || currentMessage != next || currentMood != incoming[0]) generation++;
        currentMood = incoming[0];
        currentMessage = next;
        liveMode = true;
        lastUpdate = lastContact = millis();
        Serial.println("CANVAS_OK");
      }
      incoming = "";
    } else if (c != '\r') {
      if (incoming.length() < 400) incoming += c;
      else incoming = "";
    }
  }
  if (liveMode && millis() - lastContact > 20000UL) enterDemo();
}

void setup() {
  Serial.begin(115200);
  incoming.reserve(400);
  matrix.begin();
  matrix.textFont(Font_5x7);
  matrix.textScrollSpeed(SCROLL_STEP_MS);
  matrix.clear();
}

void loop() {
  receiveUpdate();
  if (!liveMode) {
    scrollMessage("   Waiting for Canvas key   ");
    return;
  }
  if (millis() - lastUpdate > 900000UL) {
    scrollMessage("   Canvas update overdue - last saved: " + currentMessage);
  } else if (currentMood == 'I') {
    scrollMessage(currentMessage);
    pumpWait(500);
  } else {
    showMessage(currentMessage, currentMood == 'H');
  }
}
