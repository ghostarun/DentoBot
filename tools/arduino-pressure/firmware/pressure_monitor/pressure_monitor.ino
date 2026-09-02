/*
 * DENTOBOT pneumatic pressure firmware for Arduino UNO WiFi R4.
 *
 * Line format expected by pressure_monitor.py:
 *   seq,micros,raw_adc
 *
 * 14-bit ADC, 460800 baud, NXP MPX5700 on A0.
 * Default sample rate 1000 Hz. MPX5700 tR typical 1.0 ms (10-90%) implies
 * analog bandwidth ~350 Hz; 1 kHz is about 3x that bandwidth (NXP MPX5700
 * Rev 10). Host may send:
 *   RATE <hz>
 * with hz in 200-1500. The sketch replies with a comment line
 *   # RATE <hz>
 * Data lines stay seq,micros,raw_adc.
 *
 * Sensing only. Does not command a robot or drill.
 */

const int PRESSURE_PIN = A0;
const int ADC_BITS = 14;
const unsigned long BAUD = 460800UL;
const int DEFAULT_HZ = 1000;
const int MIN_HZ = 200;
const int MAX_HZ = 1500;

unsigned long seq = 0;
unsigned long period_us = 1000000UL / DEFAULT_HZ;
unsigned long next_us = 0;
String cmd;

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

void pollCommand()
{
  while (Serial.available() > 0)
  {
    const char c = (char)Serial.read();
    if (c == '\n' || c == '\r')
    {
      cmd.trim();
      if (cmd.startsWith("RATE"))
      {
        const int hz = cmd.substring(4).toInt();
        if (hz > 0)
        {
          applyRate(hz);
          Serial.print("# RATE ");
          Serial.println(1000000UL / period_us);
        }
      }
      cmd = "";
    }
    else
    {
      cmd += c;
      if (cmd.length() > 40)
      {
        cmd = "";
      }
    }
  }
}

void setup()
{
  analogReadResolution(ADC_BITS);
  Serial.begin(BAUD);
  applyRate(DEFAULT_HZ);
  next_us = micros();
}

void loop()
{
  pollCommand();
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
  Serial.print(seq);
  Serial.print(',');
  Serial.print(t);
  Serial.print(',');
  Serial.println(raw);
  seq++;
}
