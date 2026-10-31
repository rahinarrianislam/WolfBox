// UNO Q demonstration: happy message first, then sad message and clock.
#include <ArduinoGraphics.h>
#include <Arduino_LED_Matrix.h>

Arduino_LED_Matrix matrix;
const unsigned long SCROLL_STEP_MS = 85;
const uint8_t HAPPY[7] = {0b0111110, 0b1000001, 0b1010101, 0b1000001, 0b1010101, 0b1001001, 0b0111110};
const uint8_t SAD[7] = {0b0111110, 0b1000001, 0b1010101, 0b1000001, 0b1001001, 0b1010101, 0b0111110};
const uint8_t CLOCK_RIM[7] = {0b0111110, 0b1000001, 0b1000001, 0b1000001, 0b1000001, 0b1000001, 0b0111110};

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
  for (int frame = 0; frame < 40; frame++) {
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
    while (millis() - started < deadline) {
      delay(1);
    }
  }
  matrix.clear();
}

// Party popper: a cone at the lower left launches confetti upward and right.
void animateConfetti() {
  const unsigned long started = millis();
  const int8_t burstX[8] = {3, 4, 5, 5, 6, 7, 8, 9};
  const int8_t burstY[8] = {1, -1, 0, 2, -2, 1, -1, 3};
  for (int frame = 0; frame < 30; frame++) {
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
    while (millis() - started < (unsigned long)(frame + 1) * 100UL) {
      delay(1);
    }
  }
  matrix.clear();
}

void showMessage(const char *message, bool happy) {
  matrix.beginText(0, 0, 127, 0, 0);
  matrix.print(message);
  matrix.endText(SCROLL_LEFT);

  const int center = 3;
  const int width = 7;
  for (int left = 13; left >= center; left--) {
    drawIcons(left, happy);
    delay(SCROLL_STEP_MS);
  }
  delay(2000);
  for (int left = center - 1; left >= -width; left--) {
    drawIcons(left, happy);
    delay(SCROLL_STEP_MS);
  }
  if (happy) {
    animateConfetti();
  } else {
    animateClock();
  }
  delay(1000);
}

void setup() {
  matrix.begin();
  matrix.textFont(Font_5x7);
  matrix.textScrollSpeed(SCROLL_STEP_MS);
  matrix.clear();
}

void loop() {
  showMessage("   No Work due, Next assignment due: N/A   ", true);
}
