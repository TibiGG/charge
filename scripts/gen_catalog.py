"""Write data/catalog.json — the curated activity shelf.

Each activity maps to one ProbLog action class (which carries the evidence) and has
the metadata the daypart/equipment filter needs. Coverage falls out of the metadata;
nothing is hand-authored per persona. Video ids were each verified against YouTube
oEmbed (exists, embeddable, title + channel) on 2026-09-18.
"""
import json
from pathlib import Path

ALL = ["none", "home", "gym"]
KIT = ["home", "gym"]
GYM = ["gym"]
DAY = ["morning", "afternoon", "evening"]


def a(id, title, action, batteries, intensity, minutes, equipment, daypart, noise, *, habits=(),
      seated=False, video=None, steps=()):
    return {"id": id, "title": title, "action": action, "batteries": batteries, "intensity": intensity,
            "duration_min": minutes, "equipment": equipment, "daypart": daypart, "noise_level": noise,
            "seated_option": seated, "habits": list(habits), "video": video, "steps": list(steps),
            "reviewed": True, "clinical_review": "pending"}


def v(video_id, title, channel, length_min):
    return {"video_id": video_id, "title": title, "channel": channel, "length_min": length_min}


ROS_BAL = v("dGCo3jX8PNs", "Exercises to improve balance and muscle strength", "Royal Osteoporosis Society", 17)

ACTIVITIES = [
    # ---- Strength / bone loading: the highest-evidence bone work needs no kit ----
    a("heel_drops", "Heel drops and stair steps", "impact_loading", ["strength"], "moderate", 10, ALL, DAY, "some",
      steps=["Stand tall. Hold a wall or a chair if you like.",
             "Rise up onto your toes. Then drop down onto your heels.",
             "Then step up and down one stair, one foot at a time.",
             "Stop if anything hurts."]),
    a("yoga_heel_drops", "Your yoga, with heel drops added", "power_yoga", ["strength", "balance"], "moderate", 25,
      ALL, ["morning", "evening"], "some", habits=["yoga"],
      video=v("eHhPe_eiCiA", "Start the Day Grounded | Morning Yoga", "Yoga With Adriene", 12),
      steps=["Do your usual yoga. This video is a good one.",
             "Between poses, rise onto your toes and drop onto your heels.",
             "Add a few small hops if that feels fine."]),
    a("ros_dance", "A short dance for your bones", "impact_loading", ["strength"], "moderate", 5, ALL, DAY, "loud",
      video=v("-NOjBAZYtsQ", "Learn a fun dance routine and improve your bone strength!", "Royal Osteoporosis Society", 1),
      steps=["Learn the moves from the video.", "Do it a few times through."]),
    a("chair_squats", "Chair squats and wall press-ups", "strength_training", ["strength"], "moderate", 15, ALL, DAY, "quiet",
      video=v("TOKxtgKrGCQ", "4 Lower Body Strength Exercises for Older Adults", "National Institute on Aging", 10),
      steps=["Sit down onto a chair and stand back up.", "Then push away from a wall with your arms."]),
    a("ros_strength_balance", "Strength and balance moves", "balance_work", ["strength", "balance"], "moderate", 17,
      ALL, DAY, "quiet", video=ROS_BAL),
    a("chair_workout", "A seated strength routine", "strength_training", ["strength", "mobility"], "gentle", 10, ALL, DAY,
      "quiet", seated=True,
      video=v("EJgZygWBKaE", "Chair-Based Exercises | 10-Minute Routine for Strength & Mobility", "CLEAR Trust", 10)),
    a("nia_strength", "A strength workout with light weights", "strength_training", ["strength"], "gentle", 27, KIT, DAY,
      "quiet", video=v("JejTelL05Qw", "Strength Training Workout for Older Adults", "National Institute on Aging", 27)),
    a("dumbbells", "A dumbbell strength workout", "strength_training", ["strength"], "moderate", 16, KIT, DAY, "some",
      video=v("p-R2QhrhdzU", "15 Minute Dumbbell Strength Workout", "The Body Coach TV by Joe Wicks", 16)),
    a("gym_machines", "A strength circuit on the machines", "strength_training", ["strength"], "moderate", 30, GYM,
      ["afternoon", "evening"], "quiet", habits=["weights"],
      steps=["Pick four machines: legs, chest, back and arms.", "Go round them in a loop."]),

    # ---- Balance & stability ----
    a("one_leg", "Stand on one leg while the kettle boils", "balance_work", ["balance"], "gentle", 5, ALL, DAY, "quiet",
      video=v("QT5d4tTXW6U", "Stand on One Foot Balance Exercise for Older Adults", "National Institute on Aging", 1),
      steps=["Hold the worktop.", "Lift one foot. Then swap."]),
    a("balance_basics", "Balance practice", "balance_work", ["balance"], "gentle", 5, ALL, DAY, "quiet",
      video=v("4YOBIEOobCE", "Balance Exercise for Older Adults", "National Institute on Aging", 1)),
    a("tai_chi", "Tai chi for balance", "balance_work", ["balance"], "gentle", 14, ALL, DAY, "quiet",
      video=v("KTba3p_bM9c", "Tai Chi for Better Balance", "SilverSneakers", 14)),
    a("tai_chi_long", "A longer tai chi practice", "balance_work", ["balance", "mobility"], "gentle", 31, ALL,
      ["morning", "evening"], "quiet",
      video=v("w_hoBMvNxGI", "30 Minute Tai Chi Practice for Balance", "Emory Goizueta Brain Health Institute", 31)),
    a("balance_walk", "Your walk, with heel-to-toe steps", "balance_walk", ["balance"], "gentle", 25, ALL,
      ["morning", "afternoon"], "quiet", habits=["walking"],
      video=v("z_GKdFf3qv4", "Heel-to-Toe Walk Balance Exercise for Older Adults", "National Institute on Aging", 1),
      steps=["Go for your usual walk.", "For a few stretches of it, walk heel to toe, like on a line."]),

    # ---- Cardio endurance / HIIT ----
    a("brisk_walk", "A brisk walk", "brisk_cardio", ["cardio"], "moderate", 30, ALL, DAY, "quiet", habits=["walking"],
      steps=["Walk fast enough to feel warm.", "You should still be able to talk."]),
    a("walk_bursts", "A walk with fast bursts", "intervals", ["peak", "cardio"], "vigorous", 20, ALL, DAY, "quiet",
      habits=["walking"], steps=["Walk at an easy pace.", "Every few minutes, go as fast as you can for a short burst."]),
    a("jw_cardio", "A beginner cardio workout", "brisk_cardio", ["cardio", "peak"], "vigorous", 16, ALL, DAY, "loud",
      video=v("1Y57LGhSdag", "15 Minute Beginner Cardio", "The Body Coach TV by Joe Wicks", 16)),
    a("jw_strength_cardio", "A strength and cardio workout", "brisk_cardio", ["cardio", "peak", "strength"], "vigorous",
      21, KIT, DAY, "loud",
      video=v("hWGKj8jbzmg", "20 Minute Strength & Cardio", "The Body Coach TV by Joe Wicks", 21)),
    a("bike_intervals", "Intervals on a bike", "intervals", ["peak", "cardio"], "vigorous", 20, KIT, DAY, "quiet",
      habits=["spin"], steps=["Ride easy to warm up.", "Then ride hard for a short burst. Then easy again. Repeat."]),
    a("lift_then_ride", "Weights, then a ride on the bike", "lift_then_ride", ["cardio"], "moderate", 20, GYM,
      ["afternoon"], "quiet", habits=["weights"], steps=["Do your usual weights.", "Then ride the bike at a steady pace."]),
    a("swim", "An easy swim", "brisk_cardio", ["cardio"], "moderate", 30, GYM, ["morning", "afternoon"], "quiet"),

    # ---- Flexibility & mobility ----
    a("desk_yoga", "Yoga for people who sit all day", "stretch_flow", ["mobility"], "gentle", 9, ALL,
      ["afternoon", "evening"], "quiet",
      video=v("a-sZbOfau6c", "Yoga for People Who Sit All Day", "Yoga With Adriene", 9)),
    a("nia_flex", "Stretches for the whole body", "stretch_flow", ["mobility"], "gentle", 18, ALL, ["morning", "evening"],
      "quiet", video=v("KcdkySvCRCc", "6 Flexibility Exercises for Older Adults", "National Institute on Aging", 18)),
    a("ros_pilates", "Gentle pilates", "stretch_flow", ["mobility", "strength"], "gentle", 14, ALL, ["morning", "evening"],
      "quiet", video=v("EUbKu27YhlQ", "Pilates exercises – modifications with osteoporosis", "Royal Osteoporosis Society", 14)),
    a("chair_yoga", "Chair yoga", "stretch_flow", ["mobility", "strength"], "gentle", 29, ALL, DAY, "quiet", seated=True,
      video=v("gXB3NhOAalk", "Chair Yoga Stretch & Strength // Seated Exercises for Seniors & Beginners",
              "SeniorShape Fitness", 29)),
    a("chair_stretch", "Seated stretches", "stretch_flow", ["mobility"], "gentle", 22, ALL, ["morning", "afternoon"],
      "quiet", seated=True,
      video=v("cgaDPZ8UdZY", "Chair Yoga for Seniors & Beginners // Energizing Seated Stretches", "SeniorShape Fitness", 22)),
]

out = Path(__file__).resolve().parents[1] / "data/catalog.json"
out.write_text(json.dumps({"_note": __doc__.strip(), "activities": ACTIVITIES}, indent=1, ensure_ascii=False))
print(len(ACTIVITIES), "activities")
