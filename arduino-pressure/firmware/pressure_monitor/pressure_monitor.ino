/*
 * DENTOBOT pneumatic pressure firmware for Arduino UNO WiFi R4.
 *
 * Line format expected by pressure_monitor.py:
 *   seq,micros,raw_adc
 * 14-bit ADC, 460800 baud, MPX5700 on A0.
 *
 * Sensing only. Does not command a robot or drill.
 */

const int pressurePin = A0;

unsigned long seq = 0;

void setup()
{
  analogReadResolution(14);
  Serial.begin(460800);
}

void loop()
{
  const int raw = analogRead(pressurePin);
  const unsigned long t = micros();

  Serial.print(seq);
  Serial.print(',');
  Serial.print(t);
  Serial.print(',');
  Serial.println(raw);

  seq++;
}
