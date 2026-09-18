/*
 * DENTOBOT pneumatic pressure firmware for Arduino UNO WiFi R4.
 *
 * Arduino IDE name: sketch (this file is the sketch entry point).
 *
 * Line format expected by pressure_monitor.py:
 *   seq,micros,raw_adc
 *
 * 14-bit ADC, NXP MPX5700 on A0. USB serial uses 460800 baud.
 * Optional WiFi: TCP server on PRESSURE_TCP_PORT (see arduino_secrets.h).
 * Same text lines and commands on USB and WiFi.
 *
 * Default sample rate 1000 Hz. Host may send:
 *   RATE <hz>
 * with hz in 200-1500. Reply comment line:
 *   # RATE <hz>
 *
 * After WiFi join, USB prints:
 *   # WIFI IP <address>
 *   # TCP port <port>
 *
 * Sensing only. Does not command a robot or drill.
 */

#include <WiFiS3.h>
#include "arduino_secrets.h"

#ifndef PRESSURE_WIFI_MODE
#if defined(PRESSURE_WIFI_ENABLE) && (PRESSURE_WIFI_ENABLE == 0)
#define PRESSURE_WIFI_MODE 0
#else
#define PRESSURE_WIFI_MODE 1
#endif
#endif

#ifndef AP_SSID
#define AP_SSID "DENTOBOT-Pressure"
#endif
#ifndef AP_PASS
#define AP_PASS "dentobot-pressure"
#endif

const int PRESSURE_PIN = A0;
const int ADC_BITS = 14;
const unsigned long BAUD = 460800UL;
const int DEFAULT_HZ = 1000;
const int MIN_HZ = 200;
const int MAX_HZ = 1500;

unsigned long seq = 0;
unsigned long period_us = 1000000UL / DEFAULT_HZ;
unsigned long next_us = 0;
String serialCmd;
String wifiCmd;

WiFiServer tcpServer(PRESSURE_TCP_PORT);
WiFiClient tcpClient;
bool wifiReady = false;

int clampHz(int hz)
{
  if (hz < MIN_HZ)
  {
    return MIN_HZ;
  }
  if (hz > MAX_HZ)
  {
    return MAX_HZ;
  }
  return hz;
}

void applyRate(int hz)
{
  hz = clampHz(hz);
  period_us = 1000000UL / (unsigned long)hz;
}

void emitLine(const String &line)
{
  Serial.println(line);
  if (tcpClient && tcpClient.connected())
  {
    tcpClient.println(line);
  }
}

void handleRateCommand(const String &cmd)
{
  if (!cmd.startsWith("RATE"))
  {
    return;
  }
  const int hz = cmd.substring(4).toInt();
  if (hz <= 0)
  {
    return;
  }
  applyRate(hz);
  String reply = "# RATE ";
  reply += String(1000000UL / period_us);
  emitLine(reply);
}

void pollCommandStream(Stream &stream, String &buffer)
{
  while (stream.available() > 0)
  {
    const char c = (char)stream.read();
    if (c == '\n' || c == '\r')
    {
      buffer.trim();
      if (buffer.length() > 0)
      {
        handleRateCommand(buffer);
      }
      buffer = "";
    }
    else
    {
      buffer += c;
      if (buffer.length() > 40)
      {
        buffer = "";
      }
    }
  }
}

void pollCommands()
{
  pollCommandStream(Serial, serialCmd);

  if (wifiReady && (!tcpClient || !tcpClient.connected()))
  {
    WiFiClient incoming = tcpServer.available();
    if (incoming)
    {
      tcpClient = incoming;
      emitLine("# WIFI client connected");
    }
  }

  if (wifiReady && tcpClient && tcpClient.connected())
  {
    pollCommandStream(tcpClient, wifiCmd);
  }
}

void announceTcpServer()
{
  wifiReady = true;
  String ipLine = "# WIFI IP ";
  ipLine += WiFi.localIP();
  emitLine(ipLine);

  String portLine = "# TCP port ";
  portLine += String(PRESSURE_TCP_PORT);
  emitLine(portLine);

  tcpServer.begin();
}

void startWifiStation()
{
  WiFi.begin(SECRET_SSID, SECRET_PASS);
  const unsigned long deadline = millis() + 60000UL;
  while (WiFi.status() != WL_CONNECTED && millis() < deadline)
  {
    delay(500);
  }
  if (WiFi.status() != WL_CONNECTED)
  {
    Serial.println("# WIFI STA failed; USB serial only");
    return;
  }
  emitLine("# WIFI mode STA");
  announceTcpServer();
}

void startWifiAccessPoint()
{
  const int status = WiFi.beginAP(AP_SSID, AP_PASS);
  if (status != WL_AP_LISTENING)
  {
    Serial.println("# WIFI AP failed; USB serial only");
    return;
  }
  emitLine("# WIFI mode AP");
  String ssidLine = "# AP SSID ";
  ssidLine += AP_SSID;
  emitLine(ssidLine);
  announceTcpServer();
}

void startWifi()
{
#if PRESSURE_WIFI_MODE == 2
  startWifiAccessPoint();
#elif PRESSURE_WIFI_MODE == 1
  startWifiStation();
#endif
}

void setup()
{
  analogReadResolution(ADC_BITS);
  Serial.begin(BAUD);
  applyRate(DEFAULT_HZ);
  next_us = micros();
#if PRESSURE_WIFI_MODE != 0
  startWifi();
#else
  Serial.println("# WIFI disabled; USB serial only (use host bridge for TCP)");
#endif
}

void loop()
{
  pollCommands();
  const unsigned long now = micros();
  if ((long)(now - next_us) < 0)
  {
    return;
  }
  next_us += period_us;
  if ((long)(now - next_us) > (long)period_us)
  {
    next_us = now;
  }

  const int raw = analogRead(PRESSURE_PIN);
  const unsigned long t = micros();

  String line;
  line.reserve(32);
  line += seq;
  line += ',';
  line += t;
  line += ',';
  line += raw;
  emitLine(line);
  seq++;
}
