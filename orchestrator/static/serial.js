/**
 * WolfBox - Arduino Desk Light Web Serial Driver (WS7)
 *
 * Vanilla JavaScript driver for Web Serial API.
 * Connects to an Arduino running firmware/desk_light/desk_light.ino at 115200 baud.
 *
 * Safe no-op in browsers lacking Web Serial support or when disconnected.
 * Never throws to the caller; catches errors and emits console warnings.
 */

(function () {
  'use strict';

  var root = typeof window !== 'undefined' ? window : (typeof globalThis !== 'undefined' ? globalThis : this);

  var port = null;
  var writer = null;
  var connected = false;
  var lastState = null;

  /**
   * Check whether the browser supports Web Serial API.
   * @returns {boolean}
   */
  function deskLightSupported() {
    try {
      return typeof navigator !== 'undefined' && 'serial' in navigator && Boolean(navigator.serial);
    } catch (e) {
      return false;
    }
  }

  /**
   * Check if a desk light is currently connected.
   * @returns {boolean}
   */
  function isDeskConnected() {
    return Boolean(connected && port && writer);
  }

  /**
   * Internal helper to clean up port and writer state.
   */
  async function disconnectCleanup() {
    connected = false;
    lastState = null;

    if (writer) {
      try {
        writer.releaseLock();
      } catch (err) {
        // Ignored
      }
      writer = null;
    }

    if (port) {
      try {
        await port.close();
      } catch (err) {
        // Ignored
      }
      port = null;
    }
  }

  /**
   * Internal helper to send a newline-terminated string to the serial port.
   * @param {string} line
   * @returns {Promise<boolean>}
   */
  async function sendLine(line) {
    if (!isDeskConnected()) {
      return false;
    }

    try {
      var encoder = new TextEncoder();
      var data = encoder.encode(line + '\n');
      await writer.write(data);
      return true;
    } catch (err) {
      console.warn('[DeskLight] Error writing to serial port:', err);
      await disconnectCleanup();
      return false;
    }
  }

  /**
   * Request serial port and connect at 115200 baud.
   * NOTE: Must be invoked from a user gesture (e.g. click event handler).
   * @returns {Promise<boolean>} true if connected, false otherwise.
   */
  async function connectDeskLight() {
    if (!deskLightSupported()) {
      console.warn('[DeskLight] Web Serial API is not supported in this browser.');
      return false;
    }

    try {
      // If already connected, close existing connection first
      if (port || writer) {
        await disconnectCleanup();
      }

      port = await navigator.serial.requestPort();
      await port.open({ baudRate: 115200 });

      if (port.writable) {
        writer = port.writable.getWriter();
        connected = true;
        lastState = null;
        console.info('[DeskLight] Successfully connected at 115200 baud.');
        return true;
      } else {
        console.warn('[DeskLight] Port opened, but writable stream is unavailable.');
        await disconnectCleanup();
        return false;
      }
    } catch (err) {
      console.warn('[DeskLight] Connection failed or was cancelled by user:', err);
      await disconnectCleanup();
      return false;
    }
  }

  /**
   * Update the desk light state: running | pass | fail | stuck | offline | idle.
   * Deduplicates calls if the state has not changed. Safe no-op if disconnected.
   * @param {string} state
   */
  function setDeskState(state) {
    if (!isDeskConnected()) {
      return;
    }

    if (!state || typeof state !== 'string') {
      return;
    }

    var normalized = state.trim().toLowerCase();
    if (normalized === lastState) {
      return;
    }

    lastState = normalized;
    sendLine('STATE ' + normalized).catch(function (err) {
      console.warn('[DeskLight] setDeskState failed:', err);
    });
  }

  /**
   * Trigger an overlay flash of n pulses, then return to previous state.
   * Safe no-op if disconnected.
   * @param {number|string} n
   */
  function flashDesk(n) {
    if (!isDeskConnected()) {
      return;
    }

    var count = parseInt(n, 10);
    if (isNaN(count) || count <= 0) {
      return;
    }

    sendLine('FLASH ' + count).catch(function (err) {
      console.warn('[DeskLight] flashDesk failed:', err);
    });
  }

  // Listen for hardware disconnection events from Web Serial API
  if (deskLightSupported()) {
    try {
      navigator.serial.addEventListener('disconnect', function (event) {
        if (port && event.port === port) {
          console.warn('[DeskLight] Serial device disconnected.');
          disconnectCleanup();
        }
      });
    } catch (err) {
      console.warn('[DeskLight] Could not bind disconnect listener:', err);
    }
  }

  // Export standalone functions
  root.deskLightSupported = deskLightSupported;
  root.connectDeskLight = connectDeskLight;
  root.setDeskState = setDeskState;
  root.flashDesk = flashDesk;
  root.isDeskConnected = isDeskConnected;

  // Export DeskLight namespace alias
  root.DeskLight = {
    supported: deskLightSupported,
    connect: connectDeskLight,
    setState: setDeskState,
    flash: flashDesk,
    isConnected: isDeskConnected
  };
})();
