"""Write a small synthetic export.xml in Apple's real export format (fixture for tests)."""
from datetime import datetime, timedelta
from pathlib import Path

out = Path(__file__).resolve().parents[1] / "data/apple_health/sample_export.xml"
end = datetime(2026, 9, 18)
tz = "+0100"
f = lambda d: d.strftime("%Y-%m-%d %H:%M:%S ") + tz
lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<!DOCTYPE HealthData [<!ELEMENT HealthData ANY>]>',
         '<HealthData locale="en_GB">', ' <ExportDate value="2026-09-18 20:00:00 +0100"/>',
         ' <Me HKCharacteristicTypeIdentifierDateOfBirth="1972-03-02" HKCharacteristicTypeIdentifierBiologicalSex="HKBiologicalSexFemale" HKCharacteristicTypeIdentifierBloodType="HKBloodTypeNotSet" HKCharacteristicTypeIdentifierFitzpatrickSkinType="HKFitzpatrickSkinTypeNotSet" HKCharacteristicTypeIdentifierCardioFitnessMedicationsUse="None"/>']
src = 'sourceName="Apple Watch" sourceVersion="11.0" device="&lt;&lt;HKDevice&gt;&gt;"'
for i in range(14):
    d = end - timedelta(days=13 - i)
    for h in range(8, 20, 2):
        lines.append(f' <Record type="HKQuantityTypeIdentifierStepCount" {src} unit="count" creationDate="{f(d)}" startDate="{f(d.replace(hour=h))}" endDate="{f(d.replace(hour=h, minute=30))}" value="{600 + (i * 37 + h * 11) % 400}"/>')
    lines.append(f' <Record type="HKQuantityTypeIdentifierRestingHeartRate" {src} unit="count/min" creationDate="{f(d)}" startDate="{f(d)}" endDate="{f(d)}" value="{61 + i % 3}"/>')
    lines.append(f' <Record type="HKQuantityTypeIdentifierAppleExerciseTime" {src} unit="min" creationDate="{f(d)}" startDate="{f(d.replace(hour=7))}" endDate="{f(d.replace(hour=8))}" value="{25 + i % 4 * 5}"/>')
    s, e = (d - timedelta(hours=1)).replace(hour=23), d.replace(hour=6, minute=20)
    lines.append(f' <Record type="HKCategoryTypeIdentifierSleepAnalysis" {src} creationDate="{f(e)}" startDate="{f(s)}" endDate="{f(e)}" value="HKCategoryValueSleepAnalysisAsleepCore"/>')
    lines.append(f' <Record type="HKCategoryTypeIdentifierSleepAnalysis" {src} creationDate="{f(e)}" startDate="{f(s)}" endDate="{f(e)}" value="HKCategoryValueSleepAnalysisInBed"/>')
    wd = d.weekday()
    plan = {0: ("Cycling", 45, 128), 2: ("Cycling", 40, 149), 4: ("TraditionalStrengthTraining", 30, 112),
            5: ("Yoga", 40, 95), 6: ("Walking", 50, 104)}
    if wd in plan:
        t, m, hr = plan[wd]
        st = d.replace(hour=7)
        lines.append(f' <Workout workoutActivityType="HKWorkoutActivityType{t}" duration="{m}" durationUnit="min" {src} creationDate="{f(st)}" startDate="{f(st)}" endDate="{f(st + timedelta(minutes=m))}">')
        lines.append(f'  <WorkoutStatistics type="HKQuantityTypeIdentifierHeartRate" startDate="{f(st)}" endDate="{f(st + timedelta(minutes=m))}" average="{hr}" minimum="90" maximum="170" unit="count/min"/>')
        lines.append(' </Workout>')
lines.append(f' <Record type="HKQuantityTypeIdentifierVO2Max" {src} unit="mL/min·kg" creationDate="{f(end)}" startDate="{f(end)}" endDate="{f(end)}" value="32.4"/>')
lines.append('</HealthData>')
out.write_text("\n".join(lines))
print(out, out.stat().st_size, "bytes")
